"""Determinism helpers.

An FYP is graded partly on reproducibility. If a reviewer reruns training and
gets a different AUC, the result is not defensible. These helpers make every
stochastic component reproducible from a single integer.
"""

from __future__ import annotations

import os
import random

__all__ = ["seed_everything", "worker_init_fn"]


def seed_everything(seed: int = 231659, deterministic: bool = False) -> int:
    """Seed Python, NumPy and torch (if installed).

    Args:
        seed: The seed value.
        deterministic: Force deterministic cuDNN kernels. Costs roughly 10-20%
            throughput, so enable it for the final reported run rather than for
            every exploratory run.

    Returns:
        The seed, so callers can log it.
    """
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)

    try:
        import numpy as np

        np.random.seed(seed)
    except ImportError:
        pass

    try:
        import torch

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
        if deterministic:
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.benchmark = False
        else:
            # benchmark=True lets cuDNN pick the fastest algorithm for our
            # fixed input size, which is a genuine speedup for CNN training.
            torch.backends.cudnn.benchmark = True
    except ImportError:
        pass

    return seed


def worker_init_fn(worker_id: int) -> None:
    """Give each DataLoader worker a distinct, reproducible seed.

    Without this, forked workers inherit the parent's RNG state and every worker
    generates the *same* augmentation sequence, silently reducing augmentation
    diversity by a factor of ``num_workers``.
    """
    import torch

    base = torch.initial_seed() % 2**32
    seed = (base + worker_id) % 2**32
    random.seed(seed)
    try:
        import numpy as np

        np.random.seed(seed)
    except ImportError:
        pass
