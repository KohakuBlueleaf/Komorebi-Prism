// Host-only helpers of the C++ drivers: .npy files, a thread pool, timing.
#pragma once

#include <atomic>
#include <cctype>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace kr {

    struct Array {
        std::vector<uint8_t> bytes;
        std::vector<size_t> shape;

        size_t size() const {
            size_t n = 1;
            for (size_t d : shape) {
                n *= d;
            }
            return n;
        }

        template <class T>
        const T* data() const {
            return reinterpret_cast<const T*>(bytes.data());
        }
    };

    inline Array load_npy(const std::string& path, size_t item_size) {
        FILE* f = std::fopen(path.c_str(), "rb");
        if (!f) {
            throw std::runtime_error("cannot open " + path);
        }
        unsigned char head[10];
        if (std::fread(head, 1, 10, f) != 10 ||
            std::memcmp(head, "\x93NUMPY", 6) != 0) {
            throw std::runtime_error("not an npy file: " + path);
        }
        size_t header_len = head[8] | (head[9] << 8);
        std::string header(header_len, ' ');
        if (std::fread(&header[0], 1, header_len, f) != header_len) {
            throw std::runtime_error("short header in " + path);
        }
        Array a;
        size_t open = header.find("'shape': (") + 10;
        size_t close = header.find(')', open);
        std::string dims = header.substr(open, close - open);
        for (size_t pos = 0; pos < dims.size();) {
            size_t used = 0;
            if (std::isdigit((unsigned char)dims[pos])) {
                a.shape.push_back(std::stoull(dims.substr(pos), &used));
                pos += used;
            } else {
                pos++;
            }
        }
        a.bytes.resize(a.size() * item_size);
        if (std::fread(a.bytes.data(), 1, a.bytes.size(), f) != a.bytes.size()) {
            throw std::runtime_error("short data in " + path);
        }
        std::fclose(f);
        return a;
    }

    inline void save_npy(
        const std::string& path,
        const void* data,
        const std::string& descr,
        const std::vector<size_t>& shape,
        size_t item_size
    ) {
        std::string dims;
        size_t count = 1;
        for (size_t d : shape) {
            dims += std::to_string(d) + (shape.size() == 1 ? "," : ", ");
            count *= d;
        }
        std::string header =
            ("{'descr': '" + descr + "', 'fortran_order': False, 'shape': (" + dims +
             "), }");
        while ((10 + header.size() + 1) % 64 != 0) {
            header += ' ';
        }
        header += '\n';
        FILE* f = std::fopen(path.c_str(), "wb");
        if (!f) {
            throw std::runtime_error("cannot write " + path);
        }
        std::fwrite("\x93NUMPY\x01\x00", 1, 8, f);
        uint16_t len = (uint16_t)header.size();
        std::fwrite(&len, 2, 1, f);
        std::fwrite(header.data(), 1, header.size(), f);
        std::fwrite(data, item_size, count, f);
        std::fclose(f);
    }

    inline void save_f32(
        const std::string& path, const float* d, const std::vector<size_t>& shape
    ) {
        save_npy(path, d, "<f4", shape, 4);
    }

    inline void save_i32(
        const std::string& path, const int32_t* d, const std::vector<size_t>& shape
    ) {
        save_npy(path, d, "<i4", shape, 4);
    }

    inline double now_ms() {
        using clock = std::chrono::steady_clock;
        return std::chrono::duration<double, std::milli>(
                   clock::now().time_since_epoch()
        )
            .count();
    }

    // Collects the per-repetition JSON records (kept only for runs of at most 100
    // repetitions) and marks the start and end of the timed loop on stderr.
    struct RepLog {
        std::string body;
        int reps = 0;
        bool keep;
        double start;

        explicit RepLog(int total) : keep(total <= 100) {
            std::fprintf(stderr, "LOOP_START\n");
            std::fflush(stderr);
            start = now_ms();
        }

        void add(const char* record) {
            if (keep) {
                body += (reps ? ", " : "");
                body += record;
            }
            reps++;
        }

        double finish() {
            double ms = now_ms() - start;
            std::fprintf(stderr, "LOOP_END\n");
            std::fflush(stderr);
            return ms;
        }
    };

    // A pool of threads that run one function at a time; thread 0 is the caller.
    class Pool {
    public:
        explicit Pool(int n) : n_(n) {
            for (int i = 1; i < n_; i++) {
                threads_.emplace_back([this, i] {
                    loop(i);
                });
            }
        }

        ~Pool() {
            {
                std::lock_guard<std::mutex> lock(m_);
                stop_ = true;
            }
            cv_.notify_all();
            for (auto& t : threads_) {
                t.join();
            }
        }

        int size() const {
            return n_;
        }

        void run(const std::function<void(int)>& fn) {
            {
                std::lock_guard<std::mutex> lock(m_);
                fn_ = &fn;
                pending_ = n_ - 1;
                generation_++;
            }
            cv_.notify_all();
            fn(0);
            std::unique_lock<std::mutex> lock(m_);
            done_.wait(lock, [this] {
                return pending_ == 0;
            });
        }

        // Calls body(begin, end) on chunks of `grain` items of [0, n), dynamically.
        void for_chunks(
            int64_t n, int64_t grain, const std::function<void(int64_t, int64_t)>& body
        ) {
            std::atomic<int64_t> next{0};
            run([&](int) {
                for (;;) {
                    int64_t begin = next.fetch_add(grain);
                    if (begin >= n) {
                        return;
                    }
                    body(begin, begin + grain < n ? begin + grain : n);
                }
            });
        }

    private:
        void loop(int index) {
            uint64_t seen = 0;
            for (;;) {
                const std::function<void(int)>* fn;
                {
                    std::unique_lock<std::mutex> lock(m_);
                    cv_.wait(lock, [&] {
                        return stop_ || generation_ != seen;
                    });
                    if (stop_) {
                        return;
                    }
                    seen = generation_;
                    fn = fn_;
                }
                (*fn)(index);
                {
                    std::lock_guard<std::mutex> lock(m_);
                    pending_--;
                }
                done_.notify_all();
            }
        }

        int n_;
        std::vector<std::thread> threads_;
        std::mutex m_;
        std::condition_variable cv_, done_;
        const std::function<void(int)>* fn_ = nullptr;
        uint64_t generation_ = 0;
        int pending_ = 0;
        bool stop_ = false;
    };

    // Command line: --name value pairs.
    struct Args {
        std::vector<std::string> v;

        Args(int argc, char** argv) : v(argv + 1, argv + argc) {
        }

        std::string get(
            const std::string& name, const std::string& fallback = ""
        ) const {
            for (size_t i = 0; i + 1 < v.size(); i++) {
                if (v[i] == "--" + name) {
                    return v[i + 1];
                }
            }
            return fallback;
        }

        int geti(const std::string& name, int fallback) const {
            std::string s = get(name);
            return s.empty() ? fallback : std::stoi(s);
        }
    };

}  // namespace kr
