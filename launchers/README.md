# Project launchers

Platform launch scripts bootstrap the consuming Python project. Projects select and configure a launcher; this folder does not install a global commonUtils package.

macOS `.command`, Linux `.sh` and Windows `.bat` scripts share the launcher contract. See [project setup](../DEVELOPMENT.md#use-it-in-a-project).

## Files

| File | Responsibility / public entry points |
| --- | --- |
| [LaunchPythonProject_LINUX_UV.sh](LaunchPythonProject_LINUX_UV.sh) | Platform launcher. |
| [LaunchPythonProject_MAC.command](LaunchPythonProject_MAC.command) | Platform launcher. |
| [LaunchPythonProject_WIN.bat](LaunchPythonProject_WIN.bat) | Platform launcher. |

[Parent guide](../README.md)
