# dont touch files/directories with these names, or their children
ignore_names = [
    "outputs",
    "blender",
    "customgt",
    "dependencies",
    "OcMesher",
    "infinigen_gpl",
    "Blender.app",
    "build",
    "infinigen.egg-info",
]


# what is the name and email of every author
email = {
    "Alexander Raistrick": "alexemail@website.com",
    "John Smith": "johnemail@website.com",
    "Jane Doe": "janeemail@website.com",
    # others here
}
email = {"_".join(k.lower().split()): v for k, v in email.items()}

# people often use aliases or other nonstandard names. map them all back to canonical ids
# casing or spacing is automatically ignored

# people often use aliases or other nonstandard names. map them all back to canonical ids
# casing or spacing is automatically ignored
name_dedup = {
    # all lowercase name aliases of author1
    "alexander_raistrick": "alexander_raistrick",
    "alex_raistrick": "alexander_raistrick",
    "araistrick": "alexander_raistrick",
    "alexander": "alexander_raistrick",
    # all lowercase name aliases of author2
    "johnathan_smith": "john_smith",
    "johnny": "john_smith",
    # etc etc
}

# some files get mis-credited due to file moves or something else. override credit here
remap_credit = {
    "example.py": "john_smith",
}

# suffix on every commit
commit_suffix = ""  # \n\n Commit made automatically to show authorship. This commit is directly not usable."

# who should skipped files / file deletions be credited to?
neutral_author = "bot_account"
