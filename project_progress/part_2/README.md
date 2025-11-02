# Running the Notebook

## Requirements
- Python 3.9+
- Jupyter Notebook (or VS Code with the Jupyter extension)
- Data file at `../../data/productos_preprocesados.csv`

The notebook will download NLTK resources automatically.

## Quick Start
1. Open this folder in Jupyter or VS Code.
2. Open `Part2_Code.ipynb`.
3. Run all cells (Kernel → Restart & Run All).
4. If you get a file path error, edit the `csv_path` variable in the "Build inverted index" cell to the correct location of `productos_preprocesados.csv`.

## Optional (if packages are missing)
```bash
pip install numpy pandas nltk
```

## Change top-k results
You can change `top_k` in the test cells to see more/less results.
