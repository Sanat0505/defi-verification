default: thesis.pdf


thesis.pdf: thesis.tex $(wildcard content/*.tex)
	latexmk -pdf $<

clean:
	rm -f thesis.pdf
	rm -f *.{log,aux,toc,out,fls,fdb_latexmk,synctex.gz}
