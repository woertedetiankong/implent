# Sourced by the hook scripts beside it: sets $py to this machine's Python 3, or leaves it empty.
#
# Elsewhere than Windows that is python3. On Windows (hooks run in Git Bash there) python3 is often
# missing, or is the Store's stand-in that only prints how to install Python, while the real one is
# called python. So there each candidate is asked whether it is a Python 3 before it is used.
py=""
case "${OSTYPE:-}" in
  msys*|cygwin*|win32*)
    for candidate in python3 python; do
      if command -v "$candidate" >/dev/null 2>&1 &&
         "$candidate" -c 'import sys; sys.exit(sys.version_info[0] != 3)' >/dev/null 2>&1; then
        py="$candidate"
        break
      fi
    done ;;
  *)
    command -v python3 >/dev/null 2>&1 && py=python3 ;;
esac
