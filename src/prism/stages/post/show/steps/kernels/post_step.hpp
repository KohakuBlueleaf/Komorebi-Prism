// The post step of the tile thread: post_compute on the compute CPUs; post_begin
// (mover A, once a command) and post_convert (output `display`) on the data-movement
// CPUs.
#pragma once

#include "post_step.h"

#if defined(COMPILE_FOR_TRISC)
#include "compute.hpp"
#else
#include "movers.hpp"
#endif
