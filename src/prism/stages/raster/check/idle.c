/* A thread that returns at once: its regions are the run's, which the cores' commands
 * read and write, the host submitting them (check.inputs.with_thread). */
#include "kmx.h"

int kmx_main(int core) {
    (void)core;
    return 0;
}
