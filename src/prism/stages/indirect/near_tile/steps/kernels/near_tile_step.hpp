// The near tile step of the tile thread: near_tile_compute on the compute CPUs.
#pragma once

#include "near_tile_step.h"

#if defined(COMPILE_FOR_TRISC)
#include "compute.hpp"
#endif
