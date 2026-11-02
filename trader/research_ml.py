"""Research-only adapter for actual upstream rolling ML model selection.
No broker deployment until vintage fundamentals and observation provenance are certified.
"""

import logging
from pathlib import Path
import hashlib
import numpy as np
import pandas as pd
import joblib
from sklearn.preprocessing import StandardScaler
from .data import ROOT
from .db import now, dumps


def train(service, asof="2025-06-02", test_quarters=4):
    from src.strategies.ml_strategy import MLStockSelectionStrategy
    from src.strategies.base_strategy import StrategyConfig

    path = ROOT / "sample_data/fundamentals.csv.gz"
    df = pd.read_csv(path)
    asof = pd.Timestamp(asof)
    df["datadate"] = pd.to_datetime(df.datadate)
    available = pd.to_datetime(df.accepted_date, errors="coerce")
    df = df[(available.notna()) & (available < asof)].copy()
    # A forward quarterly return cannot be used as a training label before next quarter ends.
    maturity = df.datadate + pd.offsets.QuarterEnd(1) + pd.Timedelta(days=1)
    df.loc[maturity >= asof, "y_return"] = np.nan
    # Keep only explicit features: forbid future trade price, return and identifier leakage.
    features = [
        "EPS",
        "BPS",
        "DPS",
        "cur_ratio",
        "quick_ratio",
        "cash_ratio",
        "acc_rec_turnover",
        "debt_ratio",
        "debt_to_equity",
        "pe",
        "ps",
        "pb",
        "roe",
        "net_income_ratio",
        "gross_margin",
        "operating_margin",
        "asset_turnover",
        "fcf_per_share",
        "ocf_per_share",
    ]
    features = [f for f in features if f in df]
    df = df[["ticker", "datadate", "y_return"] + features].rename(
        columns={"ticker": "gvkey"}
    )
    # Select the latest quarter with broad coverage, not a single early filer's quarter.
    counts = df.groupby("datadate").gvkey.nunique()
    eligible = counts[counts >= max(10, counts.max() * 0.5)]
    if len(eligible) <= test_quarters + 1:
        raise ValueError("Insufficient available quarters for training and validation")
    df = (
        df[df.datadate <= eligible.index[-1]]
        .sort_values(["datadate", "gvkey"])
        .reset_index(drop=True)
    )

    class SafeUpstream(MLStockSelectionStrategy):
        def __init__(self):
            super().__init__(StrategyConfig(name="rolling_ml_research"))
            self.logger = logging.getLogger(__name__)

        def _prepare_supervised_dataset(self, fundamentals):
            dates = sorted(fundamentals.datadate.unique())
            boundary = dates[-1 - test_quarters]
            x = fundamentals[features].replace([np.inf, -np.inf], np.nan)
            med = x[fundamentals.datadate < boundary].median().fillna(0)
            self.prepared = x.fillna(med)
            self.medians = med
            return self.prepared, fundamentals.y_return, fundamentals.datadate

        def _build_candidate_models(self):
            self.candidates = super()._build_candidate_models()
            return self.candidates

    model = SafeUpstream()
    predictions, meta = model._rolling_train_single_date(
        df, test_quarters=test_quarters
    )
    dates = sorted(df.datadate.unique())
    boundary = dates[-1 - test_quarters]
    mask = (df.datadate < boundary) & df.y_return.notna()
    scaler = StandardScaler().fit(model.prepared[mask])
    artifact = {
        "model": model.candidates[meta["model_name"]],
        "scaler": scaler,
        "features": features,
        "medians": model.medians.to_dict(),
        "asof": str(asof.date()),
        "upstream_commit": "4409abe925c904e570be78ebfb5e77ac3491dff8",
    }
    # Upstream top-quartile positive prediction selection and equal allocator.
    threshold = max(0, float(predictions.predicted_return.quantile(0.75)))
    selected = predictions[
        (predictions.predicted_return >= threshold) & (predictions.predicted_return > 0)
    ]
    allocation = model.allocate_weights(selected, method="equal")
    report = {
        "asof": str(asof.date()),
        "metadata": meta,
        "predictions": predictions.to_dict("records"),
        "targets": allocation.to_dict("records"),
        "features": features,
        "rows": len(df),
        "status": "research only",
        "limitations": [
            "Accepted-date filter and label maturity enforced; imputation fitted only on training rows.",
            "Historical vendor snapshot may contain revised fundamentals. No certified vintage history or historical membership filter; cannot claim unbiased historical performance.",
            "Validation MSE measures prediction error, not trading profitability. Exact published ensemble not reproduced.",
        ],
    }
    with service.db.connect() as c:
        row = c.execute(
            "INSERT INTO models(created,strategy,body) VALUES(?,?,?)",
            (now(), "rolling_ml_research", dumps(report)),
        )
        mid = row.lastrowid
    target = Path(service.db.path).parent / "models"
    target.mkdir(exist_ok=True)
    artifact_path = target / f"ml-{mid}.joblib"
    joblib.dump(artifact, artifact_path)
    report["id"] = mid
    report["artifact_sha256"] = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    service.db.event(
        service.scope(),
        "ml_research_training",
        {"model_id": mid, "metadata": meta, "status": "research only"},
    )
    return report
