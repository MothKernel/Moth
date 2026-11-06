"""Offline, translated tip rotation, interleaving all three topics."""
import json
import random
from .config import ROOT

TIPS = json.loads((ROOT / 'resources/tips.json').read_text(encoding='utf-8'))


class TipDeck:
    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.pending = []

    def next(self):
        if not self.pending:
            groups = [[tip for tip in TIPS if tip['category'] == category]
                      for category in ('security', 'moth', 'nature')]
            for group in groups:
                self.rng.shuffle(group)
            self.pending = [tip for row in zip(*groups) for tip in row]
        return self.pending.pop(0)
