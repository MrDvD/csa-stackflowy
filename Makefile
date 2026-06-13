schema_dir = schema
schema_names = c_unit datapath i_prefetch io

pdf:
	cd "${schema_dir}"; \
	for name in ${schema_names}; do \
		xelatex --shell-escape -interaction=nonstopmode $${name}; \
		pdf2svg $${name}.pdf $${name}.svg ; \
	done