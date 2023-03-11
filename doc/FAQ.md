## 安装问题

1、mac上pip安装依赖包时报错：
`xcrun: error: invalid active developer path (/Library/Developer/CommandLineTools)`
原因：没有安装xcode
解决：`xcode-select --install`

2、报错：`ERROR: Could not install packages due to an OSError: Missing dependencies for SOCKS support.`
原因：开启了代理，但当前虚拟环境中没安装pysocks
解决`pip install pysocks

3、报错：`ValueError: When localhost is not accessible, a shareable link must be created. Please set share=True`
原因：终端开启了代理，gradio服务无法启动
解决：终端关闭代理后重新启动。或`python app.py --share`启动

4、windows上启动报错：`No module named 'faiss.swigfaiss_avx2`
可尝试 `conda install -c conda-forge faiss-cpu`
