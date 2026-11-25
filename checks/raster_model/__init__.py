"""The raster stage's middle pass in C and setup.h's sizes against the host model, and the
model's lists and frame pages against the reference: `python -m checks.raster_model`
prints one line a case and a JSON summary, and exits 1 on a difference. $PRISM_DATA names
the data root, $PRISM_BUILD where the C is built."""
