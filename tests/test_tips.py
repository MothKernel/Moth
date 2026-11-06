import random
from moth.tips import TIPS, TipDeck


def test_tips_cover_three_topics_without_repeating_in_a_cycle():
    deck=TipDeck(random.Random(42))
    cycle=[deck.next() for _ in range(len(TIPS))]
    assert len(TIPS)==18
    assert len({tip['id'] for tip in cycle})==18
    assert [tip['category'] for tip in cycle[:6]]==['security','moth','nature']*2
    assert deck.next()['id'] in {tip['id'] for tip in TIPS}
    for tip in TIPS:
        assert set(tip['text'])=={'en','ro','ru'}
        assert all(tip['text'].values())
        assert not tip['source'] or tip['source'].startswith('https://')
