#ifndef PHONEBOOK_SORTER_BUILD
#define PHONEBOOK_SORTER_BUILD
#endif
#include "phonebook_sorter.h"

#include <algorithm>
#include <chrono>
#include <cctype>
#include <filesystem>
#include <fstream>
#include <queue>
#include <stdexcept>
#include <string>
#include <vector>

namespace fs = std::filesystem;

struct SortConfig {
    int  column;
    bool desc;
    int  raw_key;
};

struct SplitResult {
    std::string              header;
    std::vector<std::string> chunk_names;
};

static std::size_t file_size_bytes(const std::string& filename) {
    std::error_code ec;
    auto s = fs::file_size(filename, ec);
    if (ec) return 0;
    return static_cast<std::size_t>(s);
}

static std::string trim_copy(std::string value) {
    std::size_t start = value.find_first_not_of(" \t\r\n");
    if (start == std::string::npos) return "";
    std::size_t end = value.find_last_not_of(" \t\r\n");
    return value.substr(start, end - start + 1);
}

static std::vector<std::string> parse_csv_line(const std::string& s) {
    std::vector<std::string> out;
    std::string cur;
    bool quoted = false;
    for (std::size_t i = 0; i < s.size(); ++i) {
        char c = s[i];
        if (c == '"') {
            if (quoted && i + 1 < s.size() && s[i + 1] == '"') {
                cur.push_back('"');
                ++i;
            } else {
                quoted = !quoted;
            }
        } else if (c == ',' && !quoted) {
            out.push_back(cur);
            cur.clear();
        } else {
            cur.push_back(c);
        }
    }
    out.push_back(cur);
    return out;
}

static std::string digits_only(const std::string& value) {
    std::string out;
    for (unsigned char c : value)
        if (std::isdigit(c)) out.push_back(static_cast<char>(c));
    return out;
}

static int blocked_to_int(const std::string& value) {
    std::string v = trim_copy(value);
    if (v == "\xd0\x94\xd0\xb0" ||
        v == "\xd0\xb4\xd0\xb0" ||
        v == "1" || v == "true" || v == "TRUE" || v == "yes" || v == "YES") {
        return 1;
    }
    return 0;
}

static std::string key_from_line(const std::string& line, const SortConfig& cfg) {
    auto fields = parse_csv_line(line);
    if (cfg.column < 0 || cfg.column >= static_cast<int>(fields.size())) return "";
    return trim_copy(fields[cfg.column]);
}

static int compare_phone(const std::string& a, const std::string& b) {
    std::string da = digits_only(a);
    std::string db = digits_only(b);
    auto strip = [](std::string s) -> std::string {
        auto p = s.find_first_not_of('0');
        return (p == std::string::npos) ? "0" : s.substr(p);
    };
    da = strip(da); db = strip(db);
    if (da.size() < db.size()) return -1;
    if (da.size() > db.size()) return  1;
    if (da < db) return -1;
    if (da > db) return  1;
    return 0;
}

static int compare_keys(const std::string& a, const std::string& b, int column) {
    if (column == 3) return compare_phone(a, b);
    if (column == 4) {
        int aa = blocked_to_int(a), bb = blocked_to_int(b);
        return (aa < bb) ? -1 : (aa > bb) ? 1 : 0;
    }
    if (a < b) return -1;
    if (a > b) return  1;
    return 0;
}

static bool comes_before(const std::string& la, const std::string& lb, const SortConfig& cfg) {
    std::string ka = key_from_line(la, cfg);
    std::string kb = key_from_line(lb, cfg);
    int cmp = compare_keys(ka, kb, cfg.column);
    if (cmp == 0) return la < lb;
    return cfg.desc ? cmp > 0 : cmp < 0;
}

static void sort_chunk_file(const std::string& name, const SortConfig& cfg) {
    std::ifstream in(name);
    if (!in.is_open()) throw std::runtime_error("Cannot open chunk: " + name);
    std::vector<std::string> lines;
    std::string line;
    while (std::getline(in, line))
        if (!line.empty()) lines.push_back(line);
    in.close();
    std::sort(lines.begin(), lines.end(), [&](const std::string& a, const std::string& b) {
        return comes_before(a, b, cfg);
    });
    std::ofstream out(name, std::ios::trunc);
    if (!out.is_open()) throw std::runtime_error("Cannot write chunk: " + name);
    for (const auto& l : lines) out << l << '\n';
}

static SplitResult split_to_sorted_chunks(const std::string& input, const SortConfig& cfg) {
    std::ifstream in(input);
    if (!in.is_open()) throw std::runtime_error("Cannot open input: " + input);
    std::size_t total_size = file_size_bytes(input);
    std::size_t chunk_limit = total_size / 11;
    if (chunk_limit == 0) chunk_limit = 1;
    SplitResult result;
    if (!std::getline(in, result.header)) {
        result.header = "fio,birth_date,phone_type,phone_number_raw,blocked";
        return result;
    }
    std::vector<std::string> lines;
    std::size_t current_bytes = 0;
    int chunk_id = 0;
    std::string line;
    auto flush_chunk = [&]() {
        if (lines.empty()) return;
        std::string name = "help" + std::to_string(chunk_id++) + ".txt";
        std::ofstream out(name);
        if (!out.is_open()) throw std::runtime_error("Cannot create chunk: " + name);
        for (const auto& l : lines) out << l << '\n';
        out.close();
        sort_chunk_file(name, cfg);
        result.chunk_names.push_back(name);
        lines.clear();
        current_bytes = 0;
    };
    while (std::getline(in, line)) {
        if (line.empty()) continue;
        std::size_t lb = line.size() + 1;
        if (!lines.empty() && current_bytes + lb > chunk_limit) flush_chunk();
        lines.push_back(line);
        current_bytes += lb;
    }
    flush_chunk();
    return result;
}

struct Node {
    std::string line;
    std::string key_val;
    std::size_t file_index;
    long long   order;
};

struct NodeCmp {
    SortConfig cfg;
    bool operator()(const Node& a, const Node& b) const {
        int cmp = compare_keys(a.key_val, b.key_val, cfg.column);
        if (cmp == 0) return a.order > b.order;
        return cfg.desc ? cmp < 0 : cmp > 0;
    }
};

static void merge_chunks(const SplitResult& split, const std::string& output, const SortConfig& cfg) {
    std::ofstream out(output);
    if (!out.is_open()) throw std::runtime_error("Cannot open output: " + output);
    out << split.header << '\n';
    std::vector<std::ifstream> inputs(split.chunk_names.size());
    std::priority_queue<Node, std::vector<Node>, NodeCmp> heap((NodeCmp{cfg}));
    long long order = 0;
    for (std::size_t i = 0; i < split.chunk_names.size(); ++i) {
        inputs[i].open(split.chunk_names[i]);
        if (!inputs[i].is_open()) continue;
        std::string line;
        if (std::getline(inputs[i], line))
            heap.push(Node{line, key_from_line(line, cfg), i, order++});
    }
    while (!heap.empty()) {
        Node cur = heap.top(); heap.pop();
        out << cur.line << '\n';
        std::string next_line;
        if (std::getline(inputs[cur.file_index], next_line))
            heap.push(Node{next_line, key_from_line(next_line, cfg), cur.file_index, order++});
    }
    for (auto& f : inputs) f.close();
}

static SortConfig make_config(int key) {
    int abs_key = (key < 0) ? -key : key;
    if (abs_key < 1 || abs_key > 5)
        throw std::runtime_error("Invalid key (expected 1..5 or -1..-5)");
    SortConfig cfg;
    cfg.column  = abs_key - 1;
    cfg.raw_key = key;
    if (abs_key == 5)
        cfg.desc = key > 0;
    else
        cfg.desc = key < 0;
    return cfg;
}

int SORTER_CALL sort_file(const char* input, const char* output, int key) {
    SplitResult split;
    try {
        if (!input || !output) return 1;
        SortConfig cfg = make_config(key);
        std::size_t input_size = file_size_bytes(input);
        auto t1 = std::chrono::high_resolution_clock::now();
        split = split_to_sorted_chunks(input, cfg);
        auto t2 = std::chrono::high_resolution_clock::now();
        merge_chunks(split, output, cfg);
        auto t3 = std::chrono::high_resolution_clock::now();
        double split_sec = std::chrono::duration<double>(t2 - t1).count();
        double merge_sec = std::chrono::duration<double>(t3 - t2).count();
        for (const auto& name : split.chunk_names) {
            std::error_code ec;
            fs::remove(name, ec);
        }
        return 0;
    } catch (const std::exception& e) {
        for (const auto& name : split.chunk_names) {
            std::error_code ec;
            fs::remove(name, ec);
        }
        std::ofstream err("cpp_sort_error.log", std::ios::app);
        err << e.what() << '\n';
        return 100;
    } catch (...) {
        for (const auto& name : split.chunk_names) {
            std::error_code ec;
            fs::remove(name, ec);
        }
        return 101;
    }
}
