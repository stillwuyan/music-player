import sys
import player

if __name__ == '__main__':
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    else:
        print('Need set music database path')
        exit()

    player = player.LocalPlayer()
    player.load_db(db_path)
    player.run()