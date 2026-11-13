"""Offline CLI: python -m app.ml.train --csv ml_data/synthetic_demo.csv"""
import argparse
from pathlib import Path
import pandas as pd
from .model import model_path, save_artifact, train_dataframe


def main() -> None:
    parser = argparse.ArgumentParser(description="Train held-out-evaluated Isolation Forest for access anomaly review")
    parser.add_argument("--csv", type=Path, required=True, help="Reviewed feature CSV (label/group_id/features)")
    parser.add_argument("--out", type=Path, default=model_path(), help="Trusted local model destination")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--quantile", type=float, default=0.95, help="Percentile of reviewed-normal training cohort")
    args = parser.parse_args()
    artifact, metadata = train_dataframe(pd.read_csv(args.csv), seed=args.seed, normal_quantile=args.quantile)
    save_artifact(artifact, args.out)
    print(f"Saved trusted local model to: {args.out}")
    print(f"Saved evaluation metrics to: {args.out.with_suffix('.json')}")
    print("Held-out validation (dataset-specific, not real-world detection accuracy):")
    for key, value in metadata["evaluation"].items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
