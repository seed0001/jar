Set WshShell = CreateObject("WScript.Shell")
' Get the directory of the current script
strPath = WScript.ScriptFullName
Set objFSO = CreateObject("Scripting.FileSystemObject")
Set objFile = objFSO.GetFile(strPath)
strFolder = objFSO.GetParentFolderName(objFile)

' Path to the batch file
strBatchFile = strFolder & "\start_services.bat"

' Run the batch file hidden (0 = hidden window)
WshShell.Run Chr(34) & strBatchFile & Chr(34), 0, False

Set WshShell = Nothing
