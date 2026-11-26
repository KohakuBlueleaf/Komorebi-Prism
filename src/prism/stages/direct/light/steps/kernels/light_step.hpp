// The light step of the tile thread: light_compute on the compute CPUs, light_begin on
// the data-movement CPU that takes a command first (once a command).
#pragma once

#include "light_step.h"

#if defined(COMPILE_FOR_TRISC)
#include "compute.hpp"
#else
#include "begin.hpp"
#endif
