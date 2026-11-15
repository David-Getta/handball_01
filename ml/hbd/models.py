"""Kis időbeli konvolúciós háló a testpont-sorozatra (torch).

Miért ilyen kicsi? ~800 klipünk van: egy nagy háló bemagolná a tanító
részt. Két konvolúciós réteg + átlag/max-összevonás + adatbővítés
(tükrözés, kis nagyítás, időbeli eltolás) a reális méret.
"""

from __future__ import annotations

import numpy as np

from .features import SEQ_CHANNELS, flip_sequence


def _torch():
    import torch  # lusta import: a csomag többi része torch nélkül is fut

    return torch


def build_model(n_classes: int, channels: int = SEQ_CHANNELS, width: int = 64):
    torch = _torch()
    nn = torch.nn

    class TemporalCNN(nn.Module):
        def __init__(self):
            super().__init__()
            self.net = nn.Sequential(
                nn.Conv1d(channels, width, 5, padding=2), nn.BatchNorm1d(width), nn.ReLU(),
                nn.Conv1d(width, width * 2, 5, padding=2), nn.BatchNorm1d(width * 2), nn.ReLU(),
                nn.Conv1d(width * 2, width * 2, 3, padding=1), nn.BatchNorm1d(width * 2), nn.ReLU(),
            )
            self.head = nn.Sequential(nn.Dropout(0.3), nn.Linear(width * 4, n_classes))

        def forward(self, x):  # x: (B, T, C)
            h = self.net(x.transpose(1, 2))
            return self.head(torch.cat([h.mean(-1), h.amax(-1)], 1))

    return TemporalCNN()


def _augment(batch: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    out = batch.copy()
    for i in range(len(out)):
        if rng.random() < 0.5:
            out[i] = flip_sequence(out[i])
        out[i, :, :36] *= rng.uniform(0.9, 1.1)
        shift = int(rng.integers(-2, 3))
        if shift:
            out[i] = np.roll(out[i], shift, axis=0)
    return out


class SeqClassifier:
    """sklearn-szerű burok: fit(X, y) / predict(X) / predict_proba(X), X: (N, T, C)."""

    def __init__(self, n_classes: int, epochs: int = 80, lr: float = 2e-3, batch: int = 32,
                 seed: int = 0, device: str | None = None):
        self.n_classes, self.epochs, self.lr, self.batch, self.seed = n_classes, epochs, lr, batch, seed
        torch = _torch()
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = None
        self.mu = self.sd = None

    def fit(self, X: np.ndarray, y: np.ndarray):
        torch = _torch()
        torch.manual_seed(self.seed)
        rng = np.random.default_rng(self.seed)
        self.mu = X.reshape(-1, X.shape[-1]).mean(0)
        self.sd = X.reshape(-1, X.shape[-1]).std(0) + 1e-6
        self.model = build_model(self.n_classes, X.shape[-1]).to(self.device)
        counts = np.bincount(y, minlength=self.n_classes).astype(np.float64)
        w = counts.sum() / (self.n_classes * np.maximum(counts, 1))
        loss_fn = torch.nn.CrossEntropyLoss(weight=torch.tensor(w, dtype=torch.float32, device=self.device))
        opt = torch.optim.AdamW(self.model.parameters(), lr=self.lr, weight_decay=1e-3)
        sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, self.epochs)
        self.model.train()
        for _ in range(self.epochs):
            order = rng.permutation(len(X))
            for i in range(0, len(X), self.batch):
                idx = order[i:i + self.batch]
                if len(idx) < 2:
                    continue
                xb = (_augment(X[idx], rng) - self.mu) / self.sd
                xb = torch.tensor(xb, dtype=torch.float32, device=self.device)
                yb = torch.tensor(y[idx], dtype=torch.long, device=self.device)
                opt.zero_grad()
                loss_fn(self.model(xb), yb).backward()
                opt.step()
            sched.step()
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        torch = _torch()
        self.model.eval()
        with torch.no_grad():
            xb = torch.tensor((X - self.mu) / self.sd, dtype=torch.float32, device=self.device)
            return torch.softmax(self.model(xb), -1).cpu().numpy()

    def predict(self, X: np.ndarray) -> np.ndarray:
        return self.predict_proba(X).argmax(1)

    def save(self, path) -> None:
        torch = _torch()
        torch.save({"state": self.model.state_dict(), "mu": self.mu, "sd": self.sd,
                    "n_classes": self.n_classes}, path)
