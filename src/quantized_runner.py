import logging
import gc
import torch

from config import (
    UserConfiguration,
    LogConfiguration,
    TorchConfiguration,
    TokenizerConfiguration,
    TextGenConfiguration,
    SystemConfiguration,
    TrainerConfiguration,
)

from managers import (
    OSEnvironmentManager,
    PackagePathManager,
    ModelManager,
    SystemMonitor,
    TokenizationManager,
    DataManager,
)

# TODO: These should be picked up from command line
from trainer import Trainer

from transformers import BitsAndBytesConfig

quantization_config = BitsAndBytesConfig(
    load_in_8bit=True,
    #     llm_int8_skip_modules=["lm_head"],
    #     llm_int8_threshold=3.0
)

NET_ID = "vgn2004"
ENV = "quantized"
NUM_WORKERS = 8
MAX_TOKENS = 64
MIN_GENERATION = 64
MODEL_NAME = "facebook/opt-125m"
DATASET_NAME = "NIH_ExPORTER_awarded_grant_text"
TOKENIZER_NAME = "sped_up"
BATCH_SIZE = 64

# Constants
OS_ENV_DICT = {
    "CUDA_VISIBLE_DEVICES": 0,
    "TRANSFORMERS_NO_ADVISORY_WARNINGS": "true",
    "TORCHDYNAMO_DISABLE": 1,
}

if __name__ == "__main__":
    # Clear the GPU
    torch.cuda.empty_cache()
    gc.collect()

    # Configure the logger, needed for initial utilization checks
    LogConfiguration.setup_logging()
    logger = logging.getLogger(__name__)

    # Get initial RAM and GPU utilization
    monitor = SystemMonitor()
    logger.info(f"RAM Usage: {monitor.get_ram_usage()} MB")
    logger.info(f"GPU Utilization: {monitor.get_gpu_utilization()} MB")

    # Configurations

    # Setup folder/file path related configurations
    user_config = UserConfiguration(net_id=NET_ID, env=ENV)
    system_config = SystemConfiguration(num_workers=NUM_WORKERS)
    tokenizer_config = TokenizerConfiguration(
        max_tokens=MAX_TOKENS, tokenizer_name=TOKENIZER_NAME
    )
    torch_config = TorchConfiguration()
    torch_config.commit()

    # System configurations

    # Add Python packages to sys path
    package_path_manager = PackagePathManager(user_config)
    package_path_manager.add_package_paths_to_system()

    # Add environment variables to OS env
    os_env_manager = OSEnvironmentManager()
    os_env_manager.update_from_dict(OS_ENV_DICT)

    # Tokenization
    tokenization_manager = TokenizationManager(user_config, tokenizer_config)
    tokenization_manager.load_for_model(MODEL_NAME)

    # Datasets
    data_manager = DataManager(user_config, system_config, tokenizer_config)
    data_manager.dataset_name = DATASET_NAME
    data_manager.set_data_collator(tokenization_manager.tokenizer)

    # Tokenize dataset from scratch (skipped)
    #     data_manager.create_dataset_from_jsonl_zst_file(name=DATASET_NAME,
    #                                                     jsonl_zst_file_path="E:\\NIH_ExPORTER_awarded_grant_text.jsonl.zst")
    #     data_manager.create_tokenized_dataset()
    #     training_dataset, validation_dataset = data_manager.fetch_train_validation_split()

    # Load from disk
    try:
        (
            training_dataset,
            validation_dataset,
        ) = data_manager.fetch_train_validation_split_from_disk()
    except FileNotFoundError as fe:
        logger.warning(f"{fe.__repr__()}")
        data_manager.create_dataset_from_jsonl_zst_file(
            name=DATASET_NAME,
            jsonl_zst_file_path="/scratch/vgn2004/fine_tuning/datasets/NIH_ExPORTER_awarded_grant_text.jsonl.zst",
        )
        data_manager.create_tokenized_dataset(tokenization_manager.tokenize)
        (
            training_dataset,
            validation_dataset,
        ) = data_manager.fetch_train_validation_split()

    # Dataloaders
    training_dataloader, validation_dataloader = data_manager.fetch_dataloaders(
        training_dataset=training_dataset,
        validation_dataset=validation_dataset,
        batch_size=BATCH_SIZE,
    )

    # Model
    model_manager = ModelManager(system_config)
    model_manager.load(MODEL_NAME, quantization_config=quantization_config)
    logger.info(model_manager.model)

    # Text Generation
    text_gen_config = TextGenConfiguration(
        tokenization_manager.tokenizer, min_tokens_to_generate=MIN_GENERATION
    )
    prompt = tokenization_manager.encode("This")
    sequence = model_manager.infer(prompt, text_gen_config)
    text = tokenization_manager.decode(sequence, text_gen_config)
    logging.info(f"Generated Text Before Fine-Tuning:\n{text}")

    # Training
    train_config = TrainerConfiguration()
    trainer = Trainer(
        model_name=MODEL_NAME,
        user_config=user_config,
        system_config=system_config,
        tokenizer_config=tokenizer_config,
        text_gen_config=text_gen_config,
        train_config=train_config,
        data_manager=data_manager,
        model_manager=model_manager,
        tokenization_manager=tokenization_manager,
        training_dataloader=training_dataloader,
        validation_dataloader=validation_dataloader,
    )
    trainer.run()
