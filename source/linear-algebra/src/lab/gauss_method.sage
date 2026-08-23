# Tampilkan langkah-langkah metode Gauss dan reduksi Gauss--Jordan.
# 2012-Apr-20  Jim Hefferon  Public Domain. 
# 2019-Nov-09 JH  Perubahan kecil pada format
# 2021-Sep-22 JH  Penyesuaian untuk Python 3

# Reduksi Gauss sederhana
def gauss_method(M,rescale_leading_entry=False):
    """Uraikan reduksi matriks rasional yang diberikan ke bentuk eselon.
      M  matriks rasional   misalnya M = matrix(QQ, [[..], [..], ..])
      rescale_leading_entry=False  boolean  ubah entri utama menjadi 1
    Mengembalikan: None.  Efek samping: M direduksi dan langkah-langkahnya
    dicetak. Perhatikan bahwa hasilnya berbentuk eselon, bukan bentuk eselon
    tereduksi, dan prosedur ini tidak selalu berakhir sama seperti
    M.echelon_form().
    """
    num_rows=M.nrows()
    num_cols=M.ncols()
    print(M)    

    col = 0   # semua kolom sebelumnya sudah selesai
    for row in range(0,num_rows): 
        # Perlukah kita menukar masuk sebuah entri tak nol dari bawah?
        while (col < num_cols
               and M[row][col] == 0): 
            for i in M.nonzero_positions_in_column(col):
                if i > row:
                    print(" tukar baris", row+1, "dengan baris", i+1)
                    M.swap_rows(row,i)
                    print(M)
                    break     
            else:
                col += 1

        if col >= num_cols:
            break
       
        # Sekarang dijamin bahwa M[row][col] != 0
        if (rescale_leading_entry
           and M[row][col] != 1):
            print(" ambil", 1/M[row][col], "kali baris", row+1)
            M.rescale_row(row,1/M[row][col])
            print(M) 
        change_flag=False
        for changed_row in range(row+1,num_rows):
            if M[changed_row][col] != 0:
                change_flag=True
                factor=-1*M[changed_row][col]/M[row][col]
                print(" ambil", factor, "kali baris", row+1, "ditambah baris", changed_row+1)
                M.add_multiple_of_row(changed_row,row,factor)
        if change_flag:
            print(M)
        col +=1

# Reduksi Gauss--Jordan sederhana
def gauss_jordan(M):
    """Uraikan reduksi matriks rasional yang diberikan ke bentuk eselon
    tereduksi.
      M  matriks rasional   misalnya M = matrix(QQ, [[..], [..], ..])
    Mengembalikan: None.  Efek samping: M direduksi dan langkah-langkahnya
    dicetak.
    """
    gauss_method(M,rescale_leading_entry=False)
    # Ambil daftar entri utama [entri utama baris 0, baris 1, ...]
    pivot_list=M.pivots()
    # Skalakan ulang entri-entri utama
    change_flag=False
    for row in range(0,len(pivot_list)):
        col=pivot_list[row]
        if M[row][col] != 1:
            change_flag=True
            print(" ambil",1/M[row][col],"kali baris",row+1)
            M.rescale_row(row,1/M[row][col])
    if change_flag:
        print(M)    
    # Lakukan pemivotan
    for row in range(len(pivot_list)-1,-1,-1):
        col=pivot_list[row]
        change_flag=False
        for changed_row in range(0,row):
            if M[changed_row,col] != 0:
                change_flag=True
                factor=-1*M[changed_row][col]/M[row][col]
                print(" ambil",factor,"kali baris",row+1,"ditambah baris",changed_row+1) 
                M.add_multiple_of_row(changed_row,row,factor)
        if change_flag:
            print(M)


    
