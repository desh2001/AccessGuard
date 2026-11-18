"""Train 3 independent quarterly models; no cross-platform model fallback."""
import argparse
import json
from pathlib import Path
import pandas as pd
from .platform_models import train_all_platforms, save_platform, platform_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, default=Path("ml_data/periodic_synthetic.csv"))
    ap.add_argument("--trees", type=int, default=160)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    artifacts = train_all_platforms(pd.read_csv(args.csv), seed=args.seed, n_estimators=args.trees)
    # Train all successfully before persisting any of them.
    for key, artifact in artifacts.items():
        save_platform(artifact)
        print(f"{key}: {platform_path(key)}")
        print(json.dumps(artifact["metadata"]["evaluation"], indent=2))
    print("DEMO ONLY: Synthetic labels are not independent enterprise review outcomes.")

if __name__ == "__main__":
    main()
