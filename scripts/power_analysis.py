#!/usr/bin/env python3

import argparse
import math
from statsmodels.stats.power import FTestAnovaPower

def main():
    parser = argparse.ArgumentParser(
        description="""
        Calculate the required sample size for a one-way ANOVA using power analysis.
        
        This script uses statsmodels FTestAnovaPower.solve_power.
        
        Note on ANCOVA: You can use this for ANCOVA, but the effect size 'f' 
        should ideally be adjusted to account for the covariate's effect. 
        A tool like G*Power might be better for precise ANCOVA power analysis.
        
        Note on Repeated Measures: This script assumes independent groups and is NOT
        directly suitable for repeated measures ANOVA, which requires accounting for 
        within-subject correlations. Use tools like G*Power for repeated measures.
        """,
        formatter_class=argparse.RawTextHelpFormatter
    )

    parser.add_argument(
        "--effect-size",
        type=float,
        required=True,
        help="""Required. The anticipated effect size (Cohen's f). 
Cohen's conventions: f=0.1 (small), f=0.25 (medium), f=0.4 (large).
f = sqrt(eta_squared / (1 - eta_squared)). 
Estimate based on pilot data, prior literature, or smallest meaningful effect."""
    )
    parser.add_argument(
        "--num-groups",
        type=int,
        required=True,
        help="Required. The number of groups (k) being compared (e.g., number of distinct team structures)."
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=0.05,
        help="Significance level (alpha). Default is 0.05."
    )
    parser.add_argument(
        "--power",
        type=float,
        default=0.80,
        help="Desired statistical power (1 - beta). Default is 0.80 (80%%)."
    )

    args = parser.parse_args()

    # Input validation
    if not 0 < args.alpha < 1:
        raise ValueError("Alpha must be between 0 and 1 (exclusive).")
    if not 0 < args.power < 1:
        raise ValueError("Power must be between 0 and 1 (exclusive).")
    if args.effect_size <= 0:
        raise ValueError("Effect size (f) must be positive.")
    if args.num_groups < 2:
        raise ValueError("Number of groups must be at least 2.")

    print("--- Power Analysis Parameters ---")
    print(f"Effect Size (Cohen's f): {args.effect_size:.3f}")
    print(f"Number of Groups (k):    {args.num_groups}")
    print(f"Alpha (Significance):    {args.alpha:.3f}")
    print(f"Desired Power (1-beta):  {args.power:.3f}")
    print("-------------------------------")

    # Initialize the power analysis class
    anova_power = FTestAnovaPower()

    # Calculate required sample size
    try:
        required_n = anova_power.solve_power(
            effect_size=args.effect_size,
            power=args.power,
            alpha=args.alpha,
            k_groups=args.num_groups,
            nobs=None  # We want to solve for number of observations (sample size)
        )
        
        # The result is total N, often needs ceiling and adjustment for groups
        total_n = math.ceil(required_n)
        n_per_group = math.ceil(total_n / args.num_groups)
        # Recalculate total N based on equal group sizes
        adjusted_total_n = n_per_group * args.num_groups 

        print(f"\n--- Results ---")
        print(f"Required total sample size (N): {adjusted_total_n}")
        print(f"(Calculated as {n_per_group} participants per group for {args.num_groups} groups)")
        print("---------------\n")
        print("Important Notes:")
        print("- This total N assumes independent groups (One-Way ANOVA framework).")
        print("- For ANCOVA, ensure your effect size estimate accounts for the covariate.")
        print("- For Repeated Measures designs, use specialized tools like G*Power.")


    except Exception as e:
        print(f"\nError during power calculation: {e}")
        print("Check input parameters. Very small effect sizes might require extremely large N.")

if __name__ == "__main__":
    main()