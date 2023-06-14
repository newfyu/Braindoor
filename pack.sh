#!/bin/bash
pyinstaller braindoor.spec --clean
cp -r ./extra_files/gradio ./dist/braindoor/
cp -r ./agents ./dist/braindoor/
