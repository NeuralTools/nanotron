import os
import warnings
from pathlib import Path
from typing import Dict, List

import numpy as np
from datasets import load_from_disk

# from dataloader import get_doremi_datasets
from nanotron.config import Config, get_config_from_file

try:
    from datasets import (
        # ClassLabel,
        Dataset,
        # DatasetDict,
        Features,
        Sequence,
        Value,
    )

    # concatenate_datasets,
    # from huggingface_hub import __version__ as hf_hub_version
    from transformers import AutoTokenizer, PreTrainedTokenizerBase

    # from transformers import __version__ as tf_version
    # from transformers.trainer_pt_utils import DistributedSamplerWithLoop
except ImportError:
    warnings.warn("Datasets and/or Transformers not installed, you'll be unable to use the dataloader.")


def doremi_clm_process(
    domain_idx: int,
    raw_dataset: "Dataset",
    tokenizer: "PreTrainedTokenizerBase",
    text_column_name: str,
    dataset_processing_num_proc_per_process: int,
    dataset_overwrite_cache: bool,
    sequence_length: int,
):
    """Concatenate all texts from raw_dataset and generate chunks of `sequence_length + 1`, where chunks overlap by a single token."""
    # Adapted from https://github.com/huggingface/transformers/blob/47e1676255e5dd86b9541f734cd4f4bdcbb50f4a/examples/pytorch/language-modeling/run_clm.py#L391-L439

    def group_texts(examples: Dict[str, List[np.ndarray]]) -> Dict[str, List[np.ndarray]]:
        # Concatenate all texts.
        concatenated_examples = {k: np.concatenate(v) for k, v in examples.items()}
        total_length = len(concatenated_examples[next(iter(examples.keys()))])
        # WARNING: We drop the small remainder, we could add padding if the model supported it instead of this drop, you can
        # customize this part to your needs.
        if total_length >= sequence_length + 1:
            total_length = ((total_length - 1) // sequence_length) * sequence_length + 1
        # Split by chunks of sequence_length.
        result = {
            k: [
                t[i : i + sequence_length + 1] for i in range(0, total_length - (sequence_length + 1), sequence_length)
            ]
            for k, t in concatenated_examples.items()
        }
        result["domain_ids"] = [domain_idx] * len(result[next(iter(result.keys()))])
        return result

    def _tokenize_and_group_texts(texts: List[str]) -> Dict[str, List[np.ndarray]]:
        tokenized_batch = tokenizer.batch_encode_plus(texts, return_attention_mask=False, return_token_type_ids=False)
        tokenized_batch = {k: [np.array(tokenized_texts) for tokenized_texts in v] for k, v in tokenized_batch.items()}
        return group_texts(tokenized_batch)

    train_dataset = raw_dataset.map(
        _tokenize_and_group_texts,
        input_columns=text_column_name,
        remove_columns=raw_dataset.column_names,
        features=Features(
            {
                "input_ids": Sequence(feature=Value(dtype="int64"), length=sequence_length + 1),
                "domain_ids": Value(dtype="int64"),
            }
        ),
        batched=True,
        num_proc=1,
        writer_batch_size=1,
        # TODO: remove harcode
        # load_from_cache_file=not dataset_overwrite_cache,
        load_from_cache_file=True,
        desc=f"Grouping texts in chunks of {sequence_length+1}",
        # cache_file_name="/fsx/phuc/.cache/huggingface_cache/huggingface/modules/datasets_modules/datasets/mc4"
    )

    return train_dataset


def tokenize_dataset(config, domain_name, domain_keys, raw_dataset):
    # assert isinstance(config.data.dataset, PretrainDatasetsArgs), "Please provide a dataset in the config file"

    tokenizer_path = config.tokenizer.tokenizer_name_or_path

    tokenizer = AutoTokenizer.from_pretrained(tokenizer_path)
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "left"

    # print(f"Downloading dataset {config.data.dataset.hf_dataset_or_datasets}")

    # raw_datasets = get_doremi_datasets(
    #     hf_dataset=config.data.dataset.hf_dataset_or_datasets,
    #     domain_name=domain_name,
    #     splits=config.data.dataset.hf_dataset_splits,
    # )["train"]

    # NOTE: only for the pile splitted

    # features = Features(
    #     {"text": Value("string"), "meta": {"pile_set_name": Value("string")}, "domain": ClassLabel(names=domain_keys)}
    # )

    # raw_dataset = load_dataset(
    #     config.data.dataset.hf_dataset_or_datasets,
    #     domain_name,
    #     split=["train"],
    #     # TODO: set this in config
    #     num_proc=24,
    #     features=features,
    # )[0]

    train_dataset = doremi_clm_process(
        domain_idx=domain_idx,
        raw_dataset=raw_dataset,
        tokenizer=tokenizer,
        # text_column_name=config.data.dataset.text_column_name,
        text_column_name="text",
        dataset_processing_num_proc_per_process=3,
        dataset_overwrite_cache=config.data.dataset.dataset_overwrite_cache,
        sequence_length=1024,
    )

    return train_dataset


def find_subfolders(path):
    subfolders = []
    for entry in os.listdir(path):
        full_path = os.path.join(path, entry)
        if os.path.isdir(full_path):
            subfolders.append(full_path)
    return subfolders


if __name__ == "__main__":
    config_file = "/fsx/phuc/projects/nanotron/examples/doremi/config_100m_llama.yaml"
    raw_file_path = "/fsx/phuc/project_data/doremi/datasets/the_pile_raw/splitted"
    save_path = "/fsx/phuc/project_data/doremi/datasets/the_pile_raw/tokenized_data_separate"
    # save_path = "/fsx/phuc/project_data/doremi/datasets/the_pile_raw/tokenized_data_separate"
    # os.environ["XDG_CACHE_HOME"] = "/fsx/phuc/.cache/huggingface_cache"

    # domain_idx = int(os.environ.get("SLURM_ARRAY_TASK_ID", 0))
    domain_idx = 21
    shard_idx = int(os.environ.get("SLURM_ARRAY_TASK_ID", 0))

    # DOMAIN_KEYS = [
    #     "all",
    #     "BookCorpus2",
    #     "Books3",
    #     "Enron Emails",
    #     "EuroParl",
    #     "FreeLaw",
    #     "Gutenberg (PG-19)",
    #     "HackerNews",
    #     "NIH ExPorter",
    #     "OpenSubtitles",
    #     "OpenWebText2",
    #     "PhilPapers",
    #     "Pile-CC",
    #     "PubMed Central",
    #     "UPSTO Backgrounds",
    #     "Ubuntu IRC",
    #     "YoutubeSubtitles",
    # ]

    # NOTE: this is the one use in
    # DOMAIN_KEYS = [
    #     "Github",
    #     "FreeLaw",
    #     "OpenWebText2",
    #     "PubMed Abstracts",
    #     "DM Mathematics",
    #     "OpenSubtitles",
    #     "HackerNews",
    #     "NIH ExPorter",
    #     "PubMed Central",
    #     "Enron Emails",
    # ]

    DOMAIN_KEYS = [
        "Pile-CC",
        "Github",
        "OpenWebText2",
        "StackExchange",
        "Wikipedia (en)",
        "PubMed Abstracts",
        "USPTO Backgrounds",
        "FreeLaw",
        "PubMed Central",
        "Enron Emails",
        "HackerNews",
        "NIH ExPorter",
        "Books3",  # 12
        "ArXiv",  # 13 , launched
        "DM Mathematics",
        "OpenSubtitles",
        "Gutenberg (PG-19)",  # 16, done
        "Ubuntu IRC",  # 17, done
        "BookCorpus2",  # 18, launched
        "EuroParl",  # 19, launch
        "YoutubeSubtitles",
        "PhilPapers",
    ]

    domain_name = DOMAIN_KEYS[domain_idx]
    dataset_paths = find_subfolders(f"{raw_file_path}/{domain_name}")

    # NOTE: there are 22 domains
    # but 30 shards for each domain
    assert len(dataset_paths) == 30

    # ds = []
    # for path in dataset_paths:
    #     ds.append(load_from_disk(path)['train'])

    # from datasets import concatenate_datasets
    # raw_dataset = concatenate_datasets(ds)

    config = get_config_from_file(config_file, config_class=Config)
    print(f"domain_idx: {domain_idx}")
    print(f"shard_idx: {shard_idx}")
    print(f"domain_name: {domain_name}")
    # print(f"config.data.dataset.hf_dataset_or_datasets: {config.data.dataset.hf_dataset_or_datasets}")
    print(f"raw_file_path: {raw_file_path}")

    raw_dataset = load_from_disk(dataset_paths[shard_idx])["train"]
    train_dataset = tokenize_dataset(config, domain_name=domain_name, domain_keys=DOMAIN_KEYS, raw_dataset=raw_dataset)

    # NOTE: create a new folder for this domain
    cache_path = Path(save_path) / f"{domain_name}/{shard_idx}"
    # cache_path = Path(save_path) / f"{domain_name}"
    os.makedirs(cache_path, exist_ok=True)
    train_dataset.save_to_disk(cache_path)
