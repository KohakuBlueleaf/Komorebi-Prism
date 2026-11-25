// The stage's layouts, each in its namespace (setup.h and raster.h share names), the
// grid's words before them.
#pragma once

#include <stdint.h>

#include "../../../../core/include/grid.h"

namespace setup_k {
#include "../setup.h"
}  // namespace setup_k

namespace fill_k {
#include "../raster.h"
}  // namespace fill_k
