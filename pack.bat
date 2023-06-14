pyinstaller braindoor.spec --clean
xcopy /s /e extra_files\gradio dist\braindoor\gradio
xcopy /s /e agents dist\braindoor\agent
