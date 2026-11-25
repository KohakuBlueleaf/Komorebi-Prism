"""The frame program's compute set: one program has one, and every class it merges is
made with it."""

FRAME_COMPUTE = {
    "math_fidelity": "HiFi4",
    "fp32_dest_acc_en": True,
    "enable_trisc2_rvv": "if_present",
}
