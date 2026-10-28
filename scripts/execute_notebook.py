"""Execute this project's plain-Python notebook cells in process and save outputs.

Useful in restricted environments where Jupyter cannot open kernel sockets.
This intentionally supports the current plain-Python cells, not arbitrary magics.
Run from the repository root after installing the dev extras.
"""
from pathlib import Path
import nbformat
from IPython.core.interactiveshell import InteractiveShell
from IPython.utils.capture import capture_output

def main():
    path=Path("Payment_Fraud_Detection_&_Analytics_.ipynb")
    notebook=nbformat.read(path,as_version=4)
    shell=InteractiveShell.instance()
    count=0
    for cell in notebook.cells:
        if cell.cell_type!="code":
            continue
        count+=1
        with capture_output() as captured:
            result=shell.run_cell(cell.source,store_history=False)
        if result.error_before_exec or result.error_in_exec:
            raise RuntimeError(f"Notebook code cell {count} failed") from (result.error_before_exec or result.error_in_exec)
        cell.execution_count=count
        cell.outputs=[]
        if captured.stdout:
            cell.outputs.append(nbformat.v4.new_output("stream",name="stdout",text=captured.stdout))
        if captured.stderr:
            cell.outputs.append(nbformat.v4.new_output("stream",name="stderr",text=captured.stderr))
        for output in captured.outputs:
            cell.outputs.append(nbformat.v4.new_output("display_data",data=output.data,metadata=output.metadata))
    notebook.metadata["verification"]={"executor":"in-process IPython", "basis":"See notebook run-basis output; defaults to integration fixture"}
    nbformat.validate(notebook)
    nbformat.write(notebook,path)
    print(f"Executed {count} notebook code cells successfully")

if __name__=="__main__":
    main()
