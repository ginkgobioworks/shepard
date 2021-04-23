#
#  ________                      __      __                             ______                   __            __
# |        \                    |  \    |  \                           /      \                 |  \          |  \
#  \$$$$$$$$______    _______  _| $$_    \$$ _______    ______        |  $$$$$$\  ______    ____| $$  ______  | $$
#    | $$  /      \  /       \|   $$ \  |  \|       \  /      \       | $$   \$$ /      \  /      $$ /      \ | $$
#    | $$ |  $$$$$$\|  $$$$$$$ \$$$$$$  | $$| $$$$$$$\|  $$$$$$\      | $$      |  $$$$$$\|  $$$$$$$|  $$$$$$\| $$
#    | $$ | $$    $$ \$$    \   | $$ __ | $$| $$  | $$| $$  | $$      | $$   __ | $$  | $$| $$  | $$| $$    $$ \$$
#    | $$ | $$$$$$$$ _\$$$$$$\  | $$|  \| $$| $$  | $$| $$__| $$      | $$__/  \| $$__/ $$| $$__| $$| $$$$$$$$ __
#    | $$  \$$     \|       $$   \$$  $$| $$| $$  | $$ \$$    $$       \$$    $$ \$$    $$ \$$    $$ \$$     \|  \
#     \$$   \$$$$$$$ \$$$$$$$     \$$$$  \$$ \$$   \$$ _\$$$$$$$        \$$$$$$   \$$$$$$   \$$$$$$$  \$$$$$$$ \$$
#                                                     |  \__| $$
#                                                      \$$    $$
#                                                       \$$$$$$

#By Jacob Mevorach for Ginkgo Bioworks 2020

import os
from distutils.dir_util import copy_tree
import subprocess

def main():
    if os.getenv('ALLOW_DOCKER_ACCESS') == 'True':
        result = subprocess.call('docker pull debian',shell=True)
        if result != 0:
            raise ValueError('Could not pull debian docker container!')

    os.system('ulimit -aH')
    if os.getenv('test1') == 'test1' and os.getenv('test2') == 'test2' and os.getenv('test3') == 'test3' and str(os.getenv('test4')) == '0':
        pass
    else:
        raise ValueError('This is how it will look when shepard throws an error!')

    if os.getenv('USES_LUSTRE') == 'True':
        os.chdir(os.getenv('LUSTRE_OUTPUT_NAME'))
        os.system('dd if=/dev/zero of=outputFile bs=2G count=1')
        copy_tree(os.getenv('LUSTRE_INPUT_NAME'),os.getenv('LUSTRE_OUTPUT_NAME'))

    if os.getenv('USES_EFS') == 'True':
        os.chdir(os.getenv('EFS_OUTPUT_NAME'))
        os.system('dd if=/dev/zero of=outputFile bs=2G count=1')
        copy_tree(os.getenv('EFS_INPUT_NAME'),os.getenv('EFS_OUTPUT_NAME'))

    os.chdir(os.getenv('ROOT_OUTPUT_NAME'))
    os.system('dd if=/dev/zero of=outputFile bs=2G count=1')
    copy_tree(os.getenv('ROOT_INPUT_NAME'), os.getenv('ROOT_OUTPUT_NAME'))

    return 0

if __name__ == '__main__':
    main()