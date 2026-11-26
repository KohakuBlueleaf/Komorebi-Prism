// The toy tile thread's step `toy`: reads no list and writes nothing.
#pragma once

namespace prism_frame {
#if defined(COMPILE_FOR_TRISC)
    inline bool toy_compute(ComputeContext& ctx, const Tile& tile, Planes& planes) {
        static_cast<void>(ctx);
        static_cast<void>(tile);
        static_cast<void>(planes);
        return true;
    }
#endif
}  // namespace prism_frame
