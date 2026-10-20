"""Executable ChangeGuard Benchmark Evaluation CLI Script (Milestone 10)."""
import os
import sys
import json
import argparse

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.evaluation.evaluator import ChangeGuardEvaluator


def main():
    parser = argparse.ArgumentParser(description="Run ChangeGuard Repeatable Benchmark Evaluation.")
    parser.add_argument(
        "--provider",
        default="tfidf",
        help="AI intent model provider to evaluate ('tfidf', 'mock', etc. Default: 'tfidf')",
    )
    parser.add_argument(
        "--output-md",
        default=os.path.join("docs", "EVALUATION_REPORT.md"),
        help="Path to save generated Markdown report",
    )
    parser.add_argument(
        "--output-json",
        default=os.path.join("data", "evaluation_report.json"),
        help="Path to save structured JSON report",
    )
    args = parser.parse_args()

    print(f"============================================================")
    print(f" Starting ChangeGuard Repeatable Benchmark Evaluation")
    print(f" Provider: {args.provider}")
    print(f"============================================================")

    evaluator = ChangeGuardEvaluator()
    report = evaluator.run_evaluation(provider_name=args.provider)

    # Generate Markdown and JSON
    md_content = ChangeGuardEvaluator.generate_markdown_report(report)
    json_content = json.dumps(report.to_dict(), indent=2)

    # Print summary
    print("\n" + md_content + "\n")

    # Save to disk
    if args.output_md:
        os.makedirs(os.path.dirname(os.path.abspath(args.output_md)), exist_ok=True)
        with open(args.output_md, "w", encoding="utf-8") as f:
            f.write(md_content)
        print(f"Saved Markdown report to: {args.output_md}")

    if args.output_json:
        os.makedirs(os.path.dirname(os.path.abspath(args.output_json)), exist_ok=True)
        with open(args.output_json, "w", encoding="utf-8") as f:
            f.write(json_content)
        print(f"Saved JSON report to: {args.output_json}")

    print("============================================================")
    print(" Evaluation Completed Successfully")
    print("============================================================")


if __name__ == "__main__":
    main()
