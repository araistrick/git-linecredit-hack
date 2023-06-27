from pathlib import Path
import argparse
import subprocess
import shutil
import os
import re
import tqdm
import numpy as np
from collections import defaultdict
import time
import shlex

import logging

from config import (
    ignore_names,
    email,
    name_dedup,
    remap_credit,
    commit_suffix,
    neutral_author,
)

def parse_blame(input_path: Path, attribute_headercomments: str = None):

    with os.popen(f"git blame {input_path.absolute()}") as process:
        blame = process.readlines()

    realtext_started = False

    authorship = defaultdict(list)
    for i, l in enumerate(blame):

        s, e = l.index("("), l.index(")")

        author = "_".join(l[s + 1 : e].split()[:-4]).lower()
        linetext = l[e + 1 :].strip()

        if author in name_dedup:
            author = name_dedup[author]

        is_header = linetext.startswith("#") or linetext.startswith("//") or len(linetext) == 0

        if is_header:
            if not realtext_started and attribute_headercomments is not None:
                author = attribute_headercomments
        else:
            if not realtext_started and attribute_headercomments is not None:
                logging.debug(
                    f"In {input_path}, credited all header comments (lines before {i}) to {attribute_headercomments}"
                )
            realtext_started = True

        if any(k in str(input_path) for k in remap_credit.keys()):
            author = next(v for k, v  in remap_credit.items() if k in str(input_path))
    
        authorship[author].append(i)

    return authorship


def iter_valid_input_paths(input_repo: Path, output_repo: Path):

    for input_path in input_repo.glob("**/*"):

        input_path = input_path.absolute()

        if input_path.is_dir():
            logging.debug(f"{input_path} skipped, is a directory")
            continue
        if any(part in ignore_names for part in input_path.parts):
            logging.debug(f"{input_path} skipped, is matched by ignore_names")
            continue
        if any(part.startswith(".") for part in input_path.parts):
            logging.debug(f"{input_path} skipped, is a hidden file")
            continue

        output_path = (output_repo / (input_path.relative_to(input_repo))).absolute()

        assert output_path != input_path

        #if not output_path.exists():
        #    logging.debug(f"{input_path} skipped, does not existing in {output_repo}")
        #    continue

        try:
            input_text = input_path.read_text()
        except UnicodeDecodeError:
            logging.debug(f"{input_path} skipped, not unicode")
            continue

        yield input_path
        continue

        #if input_text != output_text:
        #    logging.debug(f"{input_path} skipped, text doesnt match {output_path}")
        #    continue

        if len(input_text.strip()) == 0:
            logging.debug(f"{input_path} skipped, no content")
            continue

        yield input_path

def fullname(id):
    author_fullname = " ".join([x.capitalize() for x in id.split("_")])
    return author_fullname


def commit_update(paths, author_id, message, dryrun_mode):

    addstr = " ".join([str(p) for p in paths])
    add_cmd = f"git add {addstr}"

    authstr = f"{fullname(author_id)} <{email[author_id]}>"
    commit_cmd = f'git commit --author "{authstr}" -m "{message + commit_suffix}"'

    logging.info(commit_cmd)

    if "commit_changes" in dryrun_mode:
        subprocess.run(shlex.split(add_cmd))
        subprocess.run(shlex.split(commit_cmd))

def insert_patch(
    curr_lines: list, 
    full_lines_text: list, 
    line_idx: int,
    allow_overwrite_line: bool = False
):

    entry = full_lines_text[line_idx]
    assert entry[0] == line_idx, (entry, line_idx)

    try:
        insert_idx = next(
            i for i, (idx, l) in enumerate(curr_lines) if idx >= line_idx
        )

        if curr_lines[insert_idx] == entry:
            return 0
        elif curr_lines[insert_idx][0] == line_idx:
            assert allow_overwrite_line
            #print("Overwrite", curr_lines[insert_idx][1][:10], "with", entry[1][:10])
            curr_lines[insert_idx] = entry
            return 1
        else:
            curr_lines.insert(insert_idx, entry)
            #print("Insert", entry[1][:10])
            return 1
        
    except StopIteration:
        curr_lines.append(entry)
        #print("Append", entry[1][:10])
        return 1

def overwrite_with_patch(curr_lines, full_lines, line_ids):
    for line_idx in line_ids:
        curr_lines[line_idx] = full_lines[line_idx]

def apply_edits_to_existing(
    edits_to_existing, 
    author: str,
    input_repo, 
    output_repo, 
    dryrun_mode
):
    
    total_lines = 0
    total_paths = []

    for input_path, author_lines in edits_to_existing:

        output_path = input_path.relative_to(input_repo)

        goal_lines = list(enumerate(input_path.read_text().splitlines(keepends=True)))
        curr_lines = list(enumerate(output_path.read_text().splitlines(keepends=True)))

        #print(f"Considering {len(author_lines)=} for {output_path=} {author=}")

        new_line_count = 0
        for i in range(len(goal_lines)):
            if i not in author_lines:
                continue
            new_line_count += insert_patch(curr_lines, goal_lines, i, allow_overwrite_line=True)

        if "change_files" in dryrun_mode:
            if output_path.exists(): # bad
                output_path.unlink()
            output_path.write_text("".join([s for i, s in curr_lines]))

        if new_line_count > 0:
            total_lines += new_line_count
            total_paths.append(output_path)

    if total_lines == 0:
        logging.warning(f"{author} didnt actually have any changes to existing files")
        return

    message = (
        f"Add {total_lines} line-edits made to existing files. Contributed as part of Infinigen-Indoors by {fullname(author)}."
    )

    commit_update(
        total_paths, 
        author, 
        message, 
        dryrun_mode
    )

def apply_authorship_commits(
    input_path, 
    output_path,
    authorship, 
    dryrun_mode,
    output_repo
):

    authors = list(set(authorship.keys()))

    linecounts = [len(authorship[k]) for k in authors]
    sort = np.argsort(linecounts)
    authors = [authors[i] for i in sort[::-1]]

    goal_lines = list(enumerate(input_path.read_text().splitlines(keepends=True)))

    curr_lines = []

    for a in authors:

        for l in authorship[a]:
            insert_patch(curr_lines, goal_lines, l)

        if "change_files" in dryrun_mode:
            if output_path.exists(): # bad
                output_path.unlink()
            output_path.parent.mkdir(exist_ok=True, parents=True)
            output_path.write_text("".join([s for i, s in curr_lines]))

        message = (
            f"Add {len(authorship[a])} lines to {output_path.relative_to(output_repo)}. Contributed as part of Infinigen-Indoors by {fullname(a)}."
        )

        commit_update([output_path], a, message, dryrun_mode)

    assert len(curr_lines) == len(goal_lines)

def reset_with_deletion_commit(file_authorships, input_repo, dryrun_mode):

    logging.info(f"Deleting {len(file_authorships)} files")
    for input_path, _ in file_authorships:
        output_relative = input_path.relative_to(input_repo)
        logging.debug(f"Deleting {output_relative}")
        if "change_files" in dryrun_mode:
            output_relative.unlink()

    commit_update(
        Path('.'),
        neutral_author,
        "Reset all files, will be recommitted with line-by-line credit",
        dryrun_mode,
    )

def compute_all_authorships(input_repo, output_repo, input_paths):
    
    file_authorships = []
    for input_path in tqdm.tqdm(input_paths):

        os.chdir(input_repo.absolute())
        authorship = parse_blame(input_path)#, attribute_headercomments=neutral_author)
        os.chdir(output_repo.absolute())

        if len(authorship) == 0:
            logging.debug(f"{input_path} skipped, blame had no lines / authors")
            continue
        if "not_committed_yet" in authorship:
            logging.debug(f"{input_path} skipped, has uncommitted changes")
            continue

        file_authorships.append((input_path, authorship))

    return file_authorships

def main(
    input_repo: Path, 
    output_repo: Path,
    dryrun_mode, 
    fresh_start=False, 
    unsafe_ignore_changes=False
):

    orig_pwd = os.getcwd()

    if dryrun_mode != "change_files,commit_changes":
        print(
            "This run is not final and will not commit. Please use --mode change_files,commit_changes "
            "if you are happy with the result and have made a backup of both repos"
        )
        time.sleep(1)

    input_paths = list(iter_valid_input_paths(input_repo, output_repo))
    
    if False:
        input_paths = [Path("/Users/araistrick/projects/indoors/setup.py")]

    file_authorships = compute_all_authorships(input_repo, output_repo, input_paths)
    print(f'Found {len(file_authorships)} valid files to be processed')

    os.chdir(output_repo.absolute())

    if False and not fresh_start:
        reset_with_deletion_commit(file_authorships, input_repo, dryrun_mode)

    if False:
        author_existingedits = {}
        for author in email.keys():
            author_existingedits[author] = []
            for input_path, authorship in file_authorships:
                if author not in authorship:
                    continue
                output_equiv = output_repo/input_path.relative_to(input_repo)
                if not output_equiv.exists():
                    continue
                author_existingedits[author].append((input_path, authorship[author]))

        for author in email.keys():

            edits_to_existing = author_existingedits[author]

            if len(edits_to_existing) == 0:
                continue

            apply_edits_to_existing(
                edits_to_existing, 
                author,
                input_repo, 
                output_repo, 
                dryrun_mode
            )

    if False:
        for author in email.keys():
            for input_path, authorship in file_authorships:
                output_path = output_repo/input_path.relative_to(input_repo)
                if not input_path.read_text() == output_path.read_text():
                    print(f"Mismatch for {input_path} and {output_path}")
                else:
                    print(f"Match for {input_path} and {output_path}")

    for input_path, authorship in file_authorships:

        output_path = output_repo/input_path.relative_to(input_repo)

        #print(input_path, output_path, output_path.exists())
        if output_path.exists():
            continue

        apply_authorship_commits(
            input_path=input_path,
            output_path=output_path,
            authorship=authorship,
            dryrun_mode=dryrun_mode,
            output_repo=output_repo
        )

    os.chdir(orig_pwd)


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("input_repo", type=Path)
    parser.add_argument("output_repo", type=Path)
    parser.add_argument(
        "--mode",
        choices=["dryrun", "change_files", "change_files,commit_changes"],
        default="dryrun",
    )
    parser.add_argument("--unsafe_ignore_changes", action="store_true")
    parser.add_argument(
        "--fresh_start",
        action="store_true",
        help="Use this option if you have not yet published your repo, and are currently on a --orphan branch",
    )
    parser.add_argument(
        "-d",
        "--debug",
        action="store_const",
        dest="loglevel",
        const=logging.DEBUG,
        default=logging.INFO,
    )
    parser.add_argument(
        "-v", "--verbose", action="store_const", dest="loglevel", const=logging.INFO
    )
    args = parser.parse_args()

    logging.basicConfig(level=args.loglevel)
    args.input_repo = args.input_repo.absolute()
    args.output_repo = args.output_repo.absolute()
    logging.info(args)

    main(
        args.input_repo,
        args.output_repo,
        dryrun_mode=args.mode,
        fresh_start=args.fresh_start,
        unsafe_ignore_changes=args.unsafe_ignore_changes,
    )
