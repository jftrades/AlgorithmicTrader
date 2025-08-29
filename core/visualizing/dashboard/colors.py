# Kontrastreichere dunkle Palette: 1=Schwarz, 2=Dark Purple, 3=Deep Blue, 4=Dark Brown, danach unterschiedliche dunkle, aber unterscheidbare Töne.
PALETTE = [
    "#000000",  # 1 primary black
    "#55309d",  # 2 lighter deep purple (was #3d2466)
    "#0b3d91",  # 3 deep blue
    "#4b2e1a",  # 4 dark brown
    "#1f5e3d",  # 5 dark green
    "#7a0c2e",  # 6 dark crimson
    "#0d4d4f",  # 7 dark teal
    "#5a3d73",  # 8 muted violet
    "#6d5600",  # 9 dark golden
    "#30343b",  # 10 graphite
]

def get_color_map(instruments):
    instruments = instruments or []
    return {inst: PALETTE[i % len(PALETTE)] for i, inst in enumerate(instruments)}
