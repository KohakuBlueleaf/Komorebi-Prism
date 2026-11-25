// The raster stage's device pieces LIGHT uses, included from stages/raster/kernels
// without a copy: its layouts (fill_k, setup_k: the directory, items, out pages, the
// give-up codes, places and wait); on the pack CPU recip and order
// (setup_k::setup_pass) and float_bits.
#pragma once

#include "../../../raster/kernels/common/layouts.hpp"
#if defined(TRISC_PACK)
#include "../../../raster/kernels/passes/clip.hpp"
#include "../../../raster/kernels/passes/vector.hpp"
#endif
