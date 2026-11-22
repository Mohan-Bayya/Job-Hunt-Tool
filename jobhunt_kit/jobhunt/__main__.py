"""Command line: python3 -m jobhunt <command>. Run from the resume folder."""
import argparse


def main():
    parser = argparse.ArgumentParser(
        prog="python3 -m jobhunt",
        description="Find matching jobs, tailor your resume for each one, and track applications.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("discover", help="find which job boards your companies use (once, then every month or two)")
    commands.add_parser("scan", help="scan thousands of company job boards for openings in India (about weekly)")
    search = commands.add_parser("search", help="fetch new postings, tailor a resume for each match, add them to the tracker")
    search.add_argument("--dry-run", action="store_true", help="list matches without saving anything")
    search.add_argument("--notify", action="store_true", help="show a macOS notification when done")
    apply = commands.add_parser("apply", help="go through the jobs waiting to be applied to and log each result")
    apply.add_argument("--no-open", action="store_true", help="don't open postings in the browser")
    commands.add_parser("run", help="search, then apply")
    commands.add_parser("sync", help="sync applications.csv with your Google Sheet (also runs during search and apply)")
    schedule = commands.add_parser("schedule", help="run the search every day")
    schedule.add_argument("--hour", type=int, default=9)
    schedule.add_argument("--minute", type=int, default=0)
    commands.add_parser("unschedule", help="stop the daily search")
    args = parser.parse_args()

    building = args.command == "run" or (args.command == "search" and not args.dry_run)
    if building:
        from .resume import is_placeholder
        if is_placeholder():
            raise SystemExit("build_resume_codes/build_resume_final.py still has the template text. "
                             "Put your own details and experience in it first (see README.md, step 3). "
                             "Add --dry-run to preview matches without building resumes.")

    if args.command == "discover":
        from .discover import discover
        discover()
    elif args.command == "sync":
        from . import sheets
        if not sheets.configured():
            raise SystemExit("Google Sheets isn't set up yet. Follow \"Optional: Google Sheet tracker\" in README.md "
                             "(SHEETS_WEBAPP_URL and SHEETS_TOKEN in jobhunt/.env).")
        summary = sheets.sync()
        print(f"Google Sheets: {sheets.describe(summary)}.")
    elif args.command == "scan":
        from .scan import scan
        scan()
    elif args.command in ("schedule", "unschedule"):
        from . import schedule as scheduler
        scheduler.install(args.hour, args.minute) if args.command == "schedule" else scheduler.uninstall()
    else:
        from . import pipeline
        if args.command in ("search", "run"):
            pipeline.search(dry_run=getattr(args, "dry_run", False), send_notification=getattr(args, "notify", False))
        if args.command in ("apply", "run"):
            pipeline.apply(open_pages=not getattr(args, "no_open", False))


if __name__ == "__main__":
    main()
