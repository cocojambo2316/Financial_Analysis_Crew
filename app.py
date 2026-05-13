# Root wrapper for Streamlit Cloud: runs src/ui/app.py
import runpy
if __name__ == '__main__':
    runpy.run_path('src/ui/app.py', run_name='__main__')
