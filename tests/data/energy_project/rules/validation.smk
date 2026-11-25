rule validate_results:
    input: "results/networks/elec_solved.nc"
    output: "results/validation.csv"
    shell: "validate {input} {output}"
