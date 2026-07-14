TF_DIR := infrastructure/terraform

.PHONY: test init plan apply destroy seed fmt

test:
	python -m pytest tests/ -v

init:
	terraform -chdir=$(TF_DIR) init

plan: init
	terraform -chdir=$(TF_DIR) plan

apply: init
	terraform -chdir=$(TF_DIR) apply

destroy:
	terraform -chdir=$(TF_DIR) destroy

fmt:
	terraform -chdir=$(TF_DIR) fmt

# Upload the sample schema contract and trigger a pipeline run with the
# sample file. Requires terraform outputs (i.e. after `make apply`).
seed:
	aws s3 cp samples/schemas/customers.json \
	  s3://$$(terraform -chdir=$(TF_DIR) output -raw config_bucket)/schemas/customers.json
	aws s3 cp samples/customers.csv \
	  s3://$$(terraform -chdir=$(TF_DIR) output -raw lake_bucket)/raw/customers/customers.csv
