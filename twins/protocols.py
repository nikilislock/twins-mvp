"""Editable interventions with hypotheses and falsifiable measurements."""
TEMPLATES = {
    "free": ("Serbest gözlem", "Observe unforced divergence in a shared world.", []),
    "direct": ("Doğrudan karşılaşma", "Both networks may respond to visible predator input.", []),
    "indirect": ("Dolaylı tehdit ipucu", "A may respond to visible B motion while its predator channel is occluded.", ["predator-mask-a"]),
    "pair": ("Ortak maruz kalma", "Compare two independent networks under shared exposure.", []),
    "social-blocked": ("Partner görüşü kapalı", "Test whether the observable partner channel contributes.", ["predator-mask-a","partner-mask-a"]),
    "visual-disabled": ("A görsel yolu kapalı", "Disable A visual input as an intervention.", ["visual-off-a"]),
    "static": ("Hareketsiz fare kontrolü", "Separate static appearance from motion and looming.", ["static"]),
    "looming": ("Yaklaşma sonrası kalıcılık", "Measure activity and recovery after predator offset.", []),
    "nociception": ("Nosiseptif duyarlılaşma", "Repeated input may change synaptic eligibility and excitability.", ["no-mouse"]),
    "odor": ("Koku eşleştirme", "Paired odor and aversive input may change subsequent response.", ["no-mouse"]),
    "habituation": ("Tekrarlanan karşılaşma", "Repeated exposure may increase, reduce, or leave response unchanged.", []),
    "zone": ("Bölge kaçınması", "Compare zone occupancy before and after thermal input.", ["no-mouse"]),
    "learning": ("Partner ve sembol protokolü", "Engineered cue and symbolic reward learning.", []),
}

def protocol_spec(name):
    if name not in TEMPLATES:
        raise ValueError("Unknown experiment")
    title, hypothesis, conditions = TEMPLATES[name]
    return dict(id=name,title=title,hypothesis=hypothesis,conditions=conditions,
                onset=50,offset=200,duration=400,intensity=.7,
                control="Matched motion, blocked partner view, static predator and disabled visual input.",
                measurement="A/B visual and descending activity; velocity; internal recovery; signed neural distance.",
                positive="A reproducible between-condition difference across seeds.",
                null="No difference, or an equivalent response to matched movement alone.")

def templates():
    return [protocol_spec(name) for name in TEMPLATES]
