from core.animation import SpriteAnimator


def test_sprite_animator_exposes_size_updates():
    # The signal lets the window follow label size animations without clipping.
    assert SpriteAnimator.size_changed is not None
