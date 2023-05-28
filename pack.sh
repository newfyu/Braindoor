#!/bin/bash
pyinstaller braindoor.spec
cp -r ./extra_files/gradio ./dist/braindoor/
cp -r ./agents ./dist/braindoor/
