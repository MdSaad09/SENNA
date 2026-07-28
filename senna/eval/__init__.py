"""The F14 evaluation suite: M1-M11 (spec 5.12) computed against the frozen model on
held-out seeds and the held-out rival band, plus the era-matched counterfactuals (F-24).

This package is the single consumer of two things training is mechanically forbidden to
touch: the reserved Stage C test seed bank (senna/train/seeds.py refuses every consumer
but this one) and the test rival band (E-06). Keeping them behind one door is what makes
"held out" a property of the code rather than a promise in a document.
"""
