Thanks for clarifying. Since both the root account is disabled **and** your regular user account is locked out after the failed LMDE 6 upgrade, you'll need to **boot into recovery mode** or use a **live USB environment** to fix things. Here's a clear plan:

---

## 🔧 **Option 1: Boot into Recovery Mode to Fix Account Access**

1. **Reboot your computer.**

2. At the **GRUB bootloader screen**, select:

   ```
   Advanced options for LMDE
   ```

3. Then select:

   ```
   LMDE 6 (recovery mode)
   ```

4. From the recovery menu, choose:

   ```
   root – Drop to root shell prompt
   ```

   > This gives you **root access** without needing a password.

5. **Remount your root filesystem as writable**:

   ```bash
   mount -o remount,rw /
   ```

6. **Unlock your user account**:

   * First, check your username:

     ```bash
     ls /home
     ```
   * Then unlock the account:

     ```bash
     usermod -U yourusername
     passwd yourusername
     ```
   * Set a new password when prompted.

7. **Enable sudo access if needed**:

   ```bash
   usermod -aG sudo yourusername
   ```

8. **Update and fix packages**:

   ```bash
   apt update
   apt install -f
   apt upgrade
   ```

9. **Reinstall cinnamon (if needed)**:

   ```bash
   apt install --reinstall cinnamon cinnamon-desktop-environment
   ```

10. **Exit and reboot**:

    ```bash
    exit
    reboot
    ```

---

## 🛠️ **Option 2: Use a Live USB to Chroot into Your System**

If recovery mode is unavailable or broken:

1. Boot from a **LMDE 6 Live USB** or any Debian-based live environment.

2. Open a terminal and mount your root partition:

   ```bash
   sudo mount /dev/sdXn /mnt
   ```

   Replace `/dev/sdXn` with your root partition (e.g., `/dev/sda2`). You can check with `lsblk`.

3. Mount necessary system dirs:

   ```bash
   sudo mount --bind /dev /mnt/dev
   sudo mount --bind /proc /mnt/proc
   sudo mount --bind /sys /mnt/sys
   sudo chroot /mnt
   ```

4. You're now in your installed system as root. Now do:

   ```bash
   usermod -U yourusername
   passwd yourusername
   usermod -aG sudo yourusername
   apt update
   apt install -f
   apt install --reinstall cinnamon
   ```

5. Exit and reboot:

   ```bash
   exit
   sudo reboot
   ```

---

Would you like help identifying your Linux partitions if you're unsure which one is root?
