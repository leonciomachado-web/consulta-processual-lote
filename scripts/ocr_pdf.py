"""OCR de PDF sem camada de texto: PyMuPDF renderiza cada página e o Tesseract (idioma por) lê.

Uso: python scripts/ocr_pdf.py <arquivo.pdf> <saida.txt> [dpi]
Requer: pip install pymupdf; Tesseract com o idioma "por". Se o Tesseract não estiver no PATH,
aponte a variável TESSERACT_EXE para o executável.
O texto sai com o cabeçalho "fonte: OCR; conferir contra o original" e uma marca por página.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def tesseract() -> str:
    exe = os.environ.get("TESSERACT_EXE") or shutil.which("tesseract")
    if not exe:
        sys.exit("Tesseract não encontrado: instale-o com o idioma 'por' ou defina TESSERACT_EXE.")
    return exe


def ocr(pdf: str, saida: str, dpi: int = 300) -> int:
    import fitz  # PyMuPDF

    exe = tesseract()
    doc = fitz.open(pdf)
    partes = [f"# fonte: OCR (Tesseract por) de {Path(pdf).name}; conferir contra o original"]
    with tempfile.TemporaryDirectory() as tmp:
        for i, pag in enumerate(doc, 1):
            png = Path(tmp) / f"p{i}.png"
            pag.get_pixmap(dpi=dpi).save(png)
            r = subprocess.run([exe, str(png), "stdout", "-l", "por", "--psm", "6"],
                               capture_output=True, text=True, encoding="utf-8")
            partes.append(f"--- página {i} ---" + chr(10) + r.stdout.strip())
    Path(saida).write_text(chr(10).join(partes) + chr(10), encoding="utf-8")
    return sum(len(p) for p in partes)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    print(ocr(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 300), "caracteres")
