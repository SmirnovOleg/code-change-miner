import multiprocessing
import os
import pickle
import sys

import config
from vcs.traverse import GitAnalyzer


def main():
    sys.setrecursionlimit(2 ** 31 - 1)
    multiprocessing.set_start_method('spawn', force=True)

    with open(os.path.join(config.DATA_ROOT, 'hashes_by_repo_name.pickle'), 'rb') as f:
        commit_filter = pickle.load(f)

    GitAnalyzer().build_change_graphs(commit_filter)


if __name__ == '__main__':
    main()
