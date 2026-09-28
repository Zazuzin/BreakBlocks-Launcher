/*
 * Native Windows entry point for the portable BreakBlocks Launcher package.
 *
 * This file deliberately avoids the C runtime. The release build links it as
 * a Windows GUI application and imports only a small set of Win32 functions.
 */

typedef unsigned int DWORD;
typedef unsigned short WORD;
typedef int BOOL;
typedef unsigned short WCHAR;
typedef void *HANDLE;
typedef void *HWND;
typedef const WCHAR *LPCWSTR;
typedef WCHAR *LPWSTR;
typedef void *LPVOID;

#define FALSE 0
#define MAX_PATH_CHARS 32768
#define CREATE_NO_WINDOW 0x08000000UL
#define STARTF_USESHOWWINDOW 0x00000001UL
#define SW_HIDE 0
#define INFINITE 0xffffffffUL
#define ERROR_SUCCESS 0UL
#define MB_ICONERROR 0x00000010UL
#define FILE_ATTRIBUTE_DIRECTORY 0x00000010UL
#define INVALID_HANDLE_VALUE ((HANDLE)(~(unsigned long long)0))

typedef struct {
    DWORD dwLowDateTime;
    DWORD dwHighDateTime;
} FILETIME;

typedef struct {
    DWORD dwFileAttributes;
    FILETIME ftCreationTime;
    FILETIME ftLastAccessTime;
    FILETIME ftLastWriteTime;
    DWORD nFileSizeHigh;
    DWORD nFileSizeLow;
    DWORD dwReserved0;
    DWORD dwReserved1;
    WCHAR cFileName[260];
    WCHAR cAlternateFileName[14];
} WIN32_FIND_DATAW;

typedef struct {
    DWORD cb;
    LPWSTR lpReserved;
    LPWSTR lpDesktop;
    LPWSTR lpTitle;
    DWORD dwX;
    DWORD dwY;
    DWORD dwXSize;
    DWORD dwYSize;
    DWORD dwXCountChars;
    DWORD dwYCountChars;
    DWORD dwFillAttribute;
    DWORD dwFlags;
    unsigned short wShowWindow;
    unsigned short cbReserved2;
    unsigned char *lpReserved2;
    HANDLE hStdInput;
    HANDLE hStdOutput;
    HANDLE hStdError;
} STARTUPINFOW;

typedef struct {
    HANDLE hProcess;
    HANDLE hThread;
    DWORD dwProcessId;
    DWORD dwThreadId;
} PROCESS_INFORMATION;

_Static_assert(sizeof(STARTUPINFOW) == 104, "Unexpected STARTUPINFOW layout");
_Static_assert(sizeof(PROCESS_INFORMATION) == 24, "Unexpected PROCESS_INFORMATION layout");
_Static_assert(sizeof(WIN32_FIND_DATAW) == 592, "Unexpected WIN32_FIND_DATAW layout");

#if defined(__GNUC__)
#define WINCALL __attribute__((ms_abi))
#else
#define WINCALL
#endif

extern DWORD WINCALL GetModuleFileNameW(HANDLE, LPWSTR, DWORD);
extern BOOL WINCALL CreateProcessW(LPCWSTR, LPWSTR, LPVOID, LPVOID, BOOL, DWORD, LPVOID, LPCWSTR, STARTUPINFOW *, PROCESS_INFORMATION *);
extern BOOL WINCALL CloseHandle(HANDLE);
extern HANDLE WINCALL FindFirstFileW(LPCWSTR, WIN32_FIND_DATAW *);
extern BOOL WINCALL FindNextFileW(HANDLE, WIN32_FIND_DATAW *);
extern BOOL WINCALL FindClose(HANDLE);
extern BOOL WINCALL DeleteFileW(LPCWSTR);
extern int WINCALL MessageBoxW(HWND, LPCWSTR, LPCWSTR, unsigned int);
extern void WINCALL ExitProcess(unsigned int);

static void clear_bytes(void *memory, DWORD size);

static DWORD string_length(const WCHAR *text) {
    DWORD length = 0;
    while (text[length]) {
        ++length;
    }
    return length;
}

static BOOL append_text(WCHAR *target, DWORD capacity, const WCHAR *text) {
    DWORD at = string_length(target);
    DWORD index = 0;
    while (text[index]) {
        if (at + index + 1 >= capacity) {
            return FALSE;
        }
        target[at + index] = text[index];
        ++index;
    }
    target[at + index] = 0;
    return 1;
}

static BOOL append_runtime_suffix(WCHAR *target, DWORD capacity) {
    DWORD at = string_length(target);
#define APPEND_RUNTIME_CHARACTER(value) do { \
        if (at + 1 >= capacity) return FALSE; \
        target[at++] = (WCHAR)(value); \
    } while (0)
    APPEND_RUNTIME_CHARACTER('r');
    APPEND_RUNTIME_CHARACTER('u');
    APPEND_RUNTIME_CHARACTER('n');
    APPEND_RUNTIME_CHARACTER('t');
    APPEND_RUNTIME_CHARACTER('i');
    APPEND_RUNTIME_CHARACTER('m');
    APPEND_RUNTIME_CHARACTER('e');
    APPEND_RUNTIME_CHARACTER('\\');
    APPEND_RUNTIME_CHARACTER('p');
    APPEND_RUNTIME_CHARACTER('y');
    APPEND_RUNTIME_CHARACTER('t');
    APPEND_RUNTIME_CHARACTER('h');
    APPEND_RUNTIME_CHARACTER('o');
    APPEND_RUNTIME_CHARACTER('n');
    APPEND_RUNTIME_CHARACTER('w');
    APPEND_RUNTIME_CHARACTER('.');
    APPEND_RUNTIME_CHARACTER('e');
    APPEND_RUNTIME_CHARACTER('x');
    APPEND_RUNTIME_CHARACTER('e');
    target[at] = 0;
#undef APPEND_RUNTIME_CHARACTER
    return 1;
}

static BOOL append_runtime_directory(WCHAR *target, DWORD capacity) {
    DWORD at = string_length(target);
#define APPEND_DIRECTORY_CHARACTER(value) do { \
        if (at + 1 >= capacity) return FALSE; \
        target[at++] = (WCHAR)(value); \
    } while (0)
    APPEND_DIRECTORY_CHARACTER('r');
    APPEND_DIRECTORY_CHARACTER('u');
    APPEND_DIRECTORY_CHARACTER('n');
    APPEND_DIRECTORY_CHARACTER('t');
    APPEND_DIRECTORY_CHARACTER('i');
    APPEND_DIRECTORY_CHARACTER('m');
    APPEND_DIRECTORY_CHARACTER('e');
    APPEND_DIRECTORY_CHARACTER('\\');
    target[at] = 0;
#undef APPEND_DIRECTORY_CHARACTER
    return 1;
}

static BOOL append_bin_directory(WCHAR *target, DWORD capacity) {
    DWORD at = string_length(target);
    if (at + 4 >= capacity) {
        return FALSE;
    }
    target[at++] = (WCHAR)'b';
    target[at++] = (WCHAR)'i';
    target[at++] = (WCHAR)'n';
    target[at++] = (WCHAR)'\\';
    target[at] = 0;
    return 1;
}

static BOOL append_zone_identifier(WCHAR *target, DWORD capacity) {
    DWORD at = string_length(target);
#define APPEND_ZONE_CHARACTER(value) do { \
        if (at + 1 >= capacity) return FALSE; \
        target[at++] = (WCHAR)(value); \
    } while (0)
    APPEND_ZONE_CHARACTER(':');
    APPEND_ZONE_CHARACTER('Z');
    APPEND_ZONE_CHARACTER('o');
    APPEND_ZONE_CHARACTER('n');
    APPEND_ZONE_CHARACTER('e');
    APPEND_ZONE_CHARACTER('.');
    APPEND_ZONE_CHARACTER('I');
    APPEND_ZONE_CHARACTER('d');
    APPEND_ZONE_CHARACTER('e');
    APPEND_ZONE_CHARACTER('n');
    APPEND_ZONE_CHARACTER('t');
    APPEND_ZONE_CHARACTER('i');
    APPEND_ZONE_CHARACTER('f');
    APPEND_ZONE_CHARACTER('i');
    APPEND_ZONE_CHARACTER('e');
    APPEND_ZONE_CHARACTER('r');
    target[at] = 0;
#undef APPEND_ZONE_CHARACTER
    return 1;
}

static void unblock_directory(const WCHAR *directory) {
    WCHAR pattern[MAX_PATH_CHARS];
    WCHAR stream[MAX_PATH_CHARS];
    WIN32_FIND_DATAW find_data;
    HANDLE search;
    DWORD at;

    clear_bytes(pattern, sizeof(pattern));
    clear_bytes(stream, sizeof(stream));
    clear_bytes(&find_data, sizeof(find_data));
    if (!append_text(pattern, MAX_PATH_CHARS, directory)) {
        return;
    }
    at = string_length(pattern);
    if (at + 1 >= MAX_PATH_CHARS) {
        return;
    }
    pattern[at++] = (WCHAR)'*';
    pattern[at] = 0;

    search = FindFirstFileW(pattern, &find_data);
    if (search == INVALID_HANDLE_VALUE) {
        return;
    }
    do {
        if (!(find_data.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY)) {
            stream[0] = 0;
            if (append_text(stream, MAX_PATH_CHARS, directory) &&
                append_text(stream, MAX_PATH_CHARS, find_data.cFileName) &&
                append_zone_identifier(stream, MAX_PATH_CHARS)) {
                DeleteFileW(stream);
            }
        }
    } while (FindNextFileW(search, &find_data));
    FindClose(search);
}

static void unblock_runtime(const WCHAR *package) {
    WCHAR runtime_directory[MAX_PATH_CHARS];
    WCHAR bin_directory[MAX_PATH_CHARS];
    clear_bytes(runtime_directory, sizeof(runtime_directory));
    clear_bytes(bin_directory, sizeof(bin_directory));
    if (!append_text(runtime_directory, MAX_PATH_CHARS, package) ||
        !append_runtime_directory(runtime_directory, MAX_PATH_CHARS)) {
        return;
    }
    unblock_directory(runtime_directory);
    if (append_text(bin_directory, MAX_PATH_CHARS, runtime_directory) &&
        append_bin_directory(bin_directory, MAX_PATH_CHARS)) {
        unblock_directory(bin_directory);
    }
}

static BOOL append_script_suffix(WCHAR *target, DWORD capacity) {
    DWORD at = string_length(target);
#define APPEND_SCRIPT_CHARACTER(value) do { \
        if (at + 1 >= capacity) return FALSE; \
        target[at++] = (WCHAR)(value); \
    } while (0)
    APPEND_SCRIPT_CHARACTER('a');
    APPEND_SCRIPT_CHARACTER('p');
    APPEND_SCRIPT_CHARACTER('p');
    APPEND_SCRIPT_CHARACTER('\\');
    APPEND_SCRIPT_CHARACTER('z');
    APPEND_SCRIPT_CHARACTER('a');
    APPEND_SCRIPT_CHARACTER('z');
    APPEND_SCRIPT_CHARACTER('u');
    APPEND_SCRIPT_CHARACTER('_');
    APPEND_SCRIPT_CHARACTER('l');
    APPEND_SCRIPT_CHARACTER('a');
    APPEND_SCRIPT_CHARACTER('u');
    APPEND_SCRIPT_CHARACTER('n');
    APPEND_SCRIPT_CHARACTER('c');
    APPEND_SCRIPT_CHARACTER('h');
    APPEND_SCRIPT_CHARACTER('e');
    APPEND_SCRIPT_CHARACTER('r');
    APPEND_SCRIPT_CHARACTER('_');
    APPEND_SCRIPT_CHARACTER('b');
    APPEND_SCRIPT_CHARACTER('o');
    APPEND_SCRIPT_CHARACTER('o');
    APPEND_SCRIPT_CHARACTER('t');
    APPEND_SCRIPT_CHARACTER('.');
    APPEND_SCRIPT_CHARACTER('p');
    APPEND_SCRIPT_CHARACTER('y');
    APPEND_SCRIPT_CHARACTER('w');
    APPEND_SCRIPT_CHARACTER('"');
    target[at] = 0;
#undef APPEND_SCRIPT_CHARACTER
    return 1;
}

static void build_error_text(WCHAR *title, WCHAR *message) {
    DWORD title_at = 0;
    DWORD message_at = 0;
#define TITLE_CHARACTER(value) title[title_at++] = (WCHAR)(value)
#define MESSAGE_CHARACTER(value) message[message_at++] = (WCHAR)(value)
    TITLE_CHARACTER('B'); TITLE_CHARACTER('r'); TITLE_CHARACTER('e'); TITLE_CHARACTER('a'); TITLE_CHARACTER('k');
    TITLE_CHARACTER('B'); TITLE_CHARACTER('l'); TITLE_CHARACTER('o'); TITLE_CHARACTER('c'); TITLE_CHARACTER('k'); TITLE_CHARACTER('s');
    TITLE_CHARACTER(' '); TITLE_CHARACTER('L'); TITLE_CHARACTER('a'); TITLE_CHARACTER('u');
    TITLE_CHARACTER('n'); TITLE_CHARACTER('c'); TITLE_CHARACTER('h'); TITLE_CHARACTER('e'); TITLE_CHARACTER('r');
    title[title_at] = 0;

    MESSAGE_CHARACTER('B'); MESSAGE_CHARACTER('r'); MESSAGE_CHARACTER('e'); MESSAGE_CHARACTER('a'); MESSAGE_CHARACTER('k');
    MESSAGE_CHARACTER('B'); MESSAGE_CHARACTER('l'); MESSAGE_CHARACTER('o'); MESSAGE_CHARACTER('c'); MESSAGE_CHARACTER('k'); MESSAGE_CHARACTER('s');
    MESSAGE_CHARACTER(' '); MESSAGE_CHARACTER('L'); MESSAGE_CHARACTER('a'); MESSAGE_CHARACTER('u');
    MESSAGE_CHARACTER('n'); MESSAGE_CHARACTER('c'); MESSAGE_CHARACTER('h'); MESSAGE_CHARACTER('e'); MESSAGE_CHARACTER('r');
    MESSAGE_CHARACTER(' '); MESSAGE_CHARACTER('c'); MESSAGE_CHARACTER('o'); MESSAGE_CHARACTER('u'); MESSAGE_CHARACTER('l'); MESSAGE_CHARACTER('d');
    MESSAGE_CHARACTER(' '); MESSAGE_CHARACTER('n'); MESSAGE_CHARACTER('o'); MESSAGE_CHARACTER('t');
    MESSAGE_CHARACTER(' '); MESSAGE_CHARACTER('s'); MESSAGE_CHARACTER('t'); MESSAGE_CHARACTER('a'); MESSAGE_CHARACTER('r'); MESSAGE_CHARACTER('t'); MESSAGE_CHARACTER('.');
    MESSAGE_CHARACTER(' '); MESSAGE_CHARACTER('R'); MESSAGE_CHARACTER('e'); MESSAGE_CHARACTER('-'); MESSAGE_CHARACTER('e'); MESSAGE_CHARACTER('x'); MESSAGE_CHARACTER('t'); MESSAGE_CHARACTER('r'); MESSAGE_CHARACTER('a'); MESSAGE_CHARACTER('c'); MESSAGE_CHARACTER('t');
    MESSAGE_CHARACTER(' '); MESSAGE_CHARACTER('t'); MESSAGE_CHARACTER('h'); MESSAGE_CHARACTER('e');
    MESSAGE_CHARACTER(' '); MESSAGE_CHARACTER('c'); MESSAGE_CHARACTER('o'); MESSAGE_CHARACTER('m'); MESSAGE_CHARACTER('p'); MESSAGE_CHARACTER('l'); MESSAGE_CHARACTER('e'); MESSAGE_CHARACTER('t'); MESSAGE_CHARACTER('e');
    MESSAGE_CHARACTER(' '); MESSAGE_CHARACTER('Z'); MESSAGE_CHARACTER('I'); MESSAGE_CHARACTER('P'); MESSAGE_CHARACTER(' '); MESSAGE_CHARACTER('a'); MESSAGE_CHARACTER('n'); MESSAGE_CHARACTER('d');
    MESSAGE_CHARACTER(' '); MESSAGE_CHARACTER('t'); MESSAGE_CHARACTER('r'); MESSAGE_CHARACTER('y'); MESSAGE_CHARACTER(' '); MESSAGE_CHARACTER('a'); MESSAGE_CHARACTER('g'); MESSAGE_CHARACTER('a'); MESSAGE_CHARACTER('i'); MESSAGE_CHARACTER('n'); MESSAGE_CHARACTER('.');
    message[message_at] = 0;
#undef TITLE_CHARACTER
#undef MESSAGE_CHARACTER
}

static BOOL package_directory(WCHAR *path, DWORD capacity) {
    DWORD length = GetModuleFileNameW((HANDLE)0, path, capacity);
    DWORD index;
    if (!length || length >= capacity) {
        return FALSE;
    }
    index = length;
    while (index && path[index - 1] != (WCHAR)'\\' && path[index - 1] != (WCHAR)'/') {
        --index;
    }
    if (!index) {
        return FALSE;
    }
    path[index] = 0;
    return 1;
}

static void clear_bytes(void *memory, DWORD size) {
    unsigned char *bytes = (unsigned char *)memory;
    DWORD index;
    for (index = 0; index < size; ++index) {
        bytes[index] = 0;
    }
}

void WINCALL launcher_entry(void) {
    WCHAR package[MAX_PATH_CHARS];
    WCHAR executable[MAX_PATH_CHARS];
    WCHAR command[MAX_PATH_CHARS];
    WCHAR error_title[32];
    WCHAR error_message[160];
    STARTUPINFOW startup;
    PROCESS_INFORMATION process;

    clear_bytes(package, sizeof(package));
    clear_bytes(executable, sizeof(executable));
    clear_bytes(command, sizeof(command));
    clear_bytes(error_title, sizeof(error_title));
    clear_bytes(error_message, sizeof(error_message));
    clear_bytes(&startup, sizeof(startup));
    clear_bytes(&process, sizeof(process));
    build_error_text(error_title, error_message);

    if (!package_directory(package, MAX_PATH_CHARS)) {
        MessageBoxW((HWND)0, error_message, error_title, MB_ICONERROR);
        ExitProcess(1);
    }

    if (!append_text(executable, MAX_PATH_CHARS, package) ||
        !append_runtime_suffix(executable, MAX_PATH_CHARS) ||
        !append_text(command, MAX_PATH_CHARS, (const WCHAR[]){'"', 0}) ||
        !append_text(command, MAX_PATH_CHARS, executable) ||
        !append_text(command, MAX_PATH_CHARS, (const WCHAR[]){'"', ' ', '"', 0}) ||
        !append_text(command, MAX_PATH_CHARS, package) ||
        !append_script_suffix(command, MAX_PATH_CHARS)) {
        MessageBoxW((HWND)0, error_message, error_title, MB_ICONERROR);
        ExitProcess(1);
    }

    unblock_runtime(package);

    startup.cb = sizeof(startup);
    startup.dwFlags = STARTF_USESHOWWINDOW;
    startup.wShowWindow = SW_HIDE;
    if (!CreateProcessW(executable, command, (LPVOID)0, (LPVOID)0, FALSE, CREATE_NO_WINDOW, (LPVOID)0, package, &startup, &process)) {
        MessageBoxW((HWND)0, error_message, error_title, MB_ICONERROR);
        ExitProcess(1);
    }

    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);
    ExitProcess(ERROR_SUCCESS);
}
