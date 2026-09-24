import argparse

STAGES = ["download", "curate", "index", "count", "enrich", "derive"]


def main(argv=None):
    parser = argparse.ArgumentParser(prog="moviewords-pipeline")
    sub = parser.add_subparsers(dest="stage", required=True)
    for stage in STAGES:
        p = sub.add_parser(stage)
        if stage == "derive":
            p.add_argument("--corpus", default="en", choices=["en", "all"])
        if stage == "count":
            p.add_argument("--workers", type=int, default=1,
                           help="parallel fetch+parse of uncached films "
                                "(use ~12 against the remote zip)")
            p.add_argument("--shard", default=None, metavar="K/N",
                           help="count only shard K of N into the cache (no "
                                "outputs); run N of these as separate "
                                "processes, then once without --shard")
    args = parser.parse_args(argv)
    # stage runners are registered as tasks land; import lazily
    from importlib import import_module
    mod = import_module(f"moviewords_pipeline.{_module_for(args.stage)}")
    if args.stage == "derive":
        mod.run(corpus=args.corpus)
    elif args.stage == "count":
        shard = tuple(map(int, args.shard.split("/"))) if args.shard else None
        mod.run(workers=args.workers, shard=shard)
    else:
        mod.run()


def _module_for(stage):
    return {"download": "download", "curate": "curate", "index": "corpus_index",
            "count": "counts", "enrich": "tmdb", "derive": "derive"}[stage]


if __name__ == "__main__":
    main()
