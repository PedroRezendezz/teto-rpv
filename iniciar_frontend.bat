@echo off
cd /d "%~dp0frontend"
set PYTHONIOENCODING=utf-8

echo.
echo  ==========================================
echo   TETO RPV - Frontend (Streamlit)
echo   Rodando em: http://localhost:8501
echo  ==========================================
echo.
echo  IMPORTANTE: o backend deve estar rodando
echo  em outra janela antes de usar o frontend.
echo.

C:\Users\pe1re\teto-rpv-venv\Scripts\streamlit run streamlit_app.py
pause
