# AccessGuard අලුත් Quarterly ML Folder — Sinhala Guide

මෙම `ml/` folder එක existing AccessGuard repository එකේ පරණ `ml/` folder එක වෙනුවට copy කරන්න.

## මේ folder එක කරන වැඩ

- Windows AD, Linux, GitHub සඳහා වෙන වෙනම Isolation Forest models train කිරීම.
- Trained model artifacts load කර 90-day account-level anomaly percentile ලබාදීම.
- Root AccessGuard backend එකෙන් එවන account feature rows validate කිරීම.
- Model එකක් නැත්නම් `model_not_trained` කියලා පැහැදිලිව return කිරීම.
- Log coverage ප්‍රමාණවත් නැත්නම් ML score නොදීම.

## මේ folder එක නොකරන දේ

- Frontend/dashboard නැහැ.
- වෙනම business database එකක් නැහැ.
- Raw logs collect කරන්නේ නැහැ.
- Employee identity resolve කරන්නේ නැහැ.
- Quarterly review tasks හදන්නේ නැහැ.
- Retain/revoke තීරණ ගන්නේ නැහැ.
- Request එකට එන batch එකෙන්ම අලුත් model එකක් train කරන්නේ නැහැ.

ඒ සියල්ල root `backend/` සහ root `frontend/` එකේ තිබිය යුතුයි.

## Repository එකට දාන ආකාරය

1. Existing repository එකේ `ml/` folder එක backup කරන්න.
2. මේ ZIP එකේ `ml/` folder එක extract කර repository root එකට copy කරන්න.
3. `AccessGuard_Antigravity_ML_Integration_Guide.md` file එක Antigravity එකට prompt එකක් විදිහට දෙන්න.
4. Antigravity එකෙන් root backend, Docker Compose, startup scripts සහ existing frontend එකට complete integration කරවන්න.
5. Root integration එක අවසන් වුණා කියලා test evidence නොමැතිව හිතන්න එපා.

## Development dataset එකෙන් train කිරීම

`AccessGuard_ML_Datasets/data/training_account_cycles.csv` එකට model schema එක ගැළපෙනවා. Windows, Linux, GitHub models තුනම train කරන්න:

```powershell
cd ml/backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:AEGIS_PLATFORM_MODEL_DIR = (Resolve-Path .\ml_artifacts\platforms).Path
python -m app.ml.platform_train --csv "C:\path\to\AccessGuard_ML_Datasets\data\training_account_cycles.csv" --trees 160 --seed 42
```

Test dataset එකේ ground truth එක feature වලට merge කරන්න එපා. වෙනම evaluation කරන්න:

```powershell
python -m app.ml.platform_evaluate_90day --features "C:\path\to\AccessGuard_ML_Datasets\data\test_90day_account_cycles.csv" --ground-truth "C:\path\to\AccessGuard_ML_Datasets\data\test_90day_ground_truth.csv"
```

මේවා synthetic data නිසා software smoke test සහ development comparison සඳහා පමණයි. Real company එකකට universal baseline එකක් නෙවෙයි.

## වැදගත්

Company එකකට actual historical baseline එකක් නැත්නම්, මුලින්ම data collect කරලා short pilot එකකදී manual review කරන්න. Verified-normal records පමණක් baseline training සඳහා භාවිත කරන්න. Confirmed concern cases evaluation සඳහා තබන්න. Unknown/evidence-gap records `normal` කියලා label කරන්න එපා. දෙවැනි blind review period එකක model එක validate කරන තුරු ML score එක production review decisions වලට trust කරන්න එපා.
