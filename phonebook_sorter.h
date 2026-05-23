#ifndef PHONEBOOK_SORTER_H
#define PHONEBOOK_SORTER_H

#ifdef _WIN32
    #define SORTER_CALL __cdecl
    #ifdef PHONEBOOK_SORTER_STATIC
        #define SORTER_API extern "C"
    #elif defined(PHONEBOOK_SORTER_BUILD)
        #define SORTER_API extern "C" __declspec(dllexport)
    #else
        #define SORTER_API extern "C" __declspec(dllimport)
    #endif
#else
    #define SORTER_CALL
    #define SORTER_API extern "C"
#endif
SORTER_API int SORTER_CALL sort_file(const char* input, const char* output, int key);
#endif
