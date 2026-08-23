# img_squeeze.sage
# Kompres gambar
# 2012-Dec-04 JH
# 2019-Nov-25 JH
# 2021-Sep-28 JH  Konversi ke Python 3
from PIL import Image

def img_squeeze(fn_in, fn_out, percent):
    """Kompres gambar menggunakan dekomposisi nilai singular.
        fn_in, fn_out  string  nama berkas
        percent  bilangan riil dalam 0..1  Fraksi nilai singular yang dipakai
    """
    if not 0 <= percent <= 1:
        raise ValueError("percent harus berada dalam rentang 0 sampai 1")
    img = Image.open(fn_in)
    img = img.convert("RGB")
    cols, rows = img.size
    dim_bound = min(rows, cols)  # untuk gambar yang tidak persegi
    cutoff = int(round(percent*dim_bound,0))
    print("gambar memiliki", rows, "baris dan", cols, "kolom")
    # Kumpulkan data dalam tiga larik, lalu berikan kepada matrix() milik Sage
    rd, gr, bl = [], [], []
    for row in range(rows):
        for a in [rd, gr, bl]:
            a.append([])
        for col in range(cols):
            r, g, b = img.getpixel((int(col), int(row)))
            rd[row].append(r)
            gr[row].append(g)
            bl[row].append(b)
    RD, GR, BL = matrix(RDF, rd), matrix(RDF, gr), matrix(RDF, bl)
    # Hitung SVD
    U_RD,Sigma_RD,V_RD = RD.SVD()
    U_GR,Sigma_GR,V_GR = GR.SVD()
    U_BL,Sigma_BL,V_BL = BL.SVD()
    # Tampilkan beberapa nilai untuk pemeriksaan
    preview_count = min(8, dim_bound)
    for i in range(preview_count):
        print("sigma_RD",i, "=%0.2f" % Sigma_RD[i][i])
    if cutoff < dim_bound:
        print("    :")  # titik-titik vertikal
        print("sigma_RD",cutoff,"=%0.2f" % Sigma_RD[cutoff][cutoff])
    else:
        print("semua", dim_bound, "nilai singular dipakai")
    if dim_bound > preview_count:
        print("    :")  # titik-titik vertikal
        for i in range(max(preview_count, dim_bound-8), dim_bound):
            print(" di bagian bawah: sigma_RD", i, "=%0.2f" % Sigma_RD[i][i])
    # Hitung sigma_1 u_1 v_1^trans + ...
    print("Hitung sigma_1 u_1 v_1^trans + ...")
    a=[]
    for i in range(rows):
        a.append([])
        for j in range(cols):
            a[i].append(0)
    A_RD, A_GR, A_BL = matrix(RDF, a), matrix(RDF, a), matrix(RDF, a)
    for i in range(cutoff):
        if (i % 10 == 0):
            print("  i=",i,"dari",cutoff)
        sigma_i = Sigma_RD[i][i]
        u_i = matrix(RDF, U_RD.column(i).column())
        v_i = matrix(RDF, V_RD.column(i).column().transpose())
        A_RD = copy(A_RD) + sigma_i*u_i*v_i
        sigma_i = Sigma_GR[i][i]
        u_i = matrix(RDF, U_GR.column(i).column())
        v_i = matrix(RDF, V_GR.column(i).column().transpose())
        A_GR = copy(A_GR) + sigma_i*u_i*v_i
        sigma_i = Sigma_BL[i][i]
        u_i = matrix(RDF, U_BL.column(i).column())
        v_i = matrix(RDF, V_BL.column(i).column().transpose())
        A_BL = copy(A_BL) + sigma_i*u_i*v_i
    # Buat gambar baru
    print("Membuat berkas gambar baru")
    img_squoze = Image.new("RGB", img.size)
    for row in range(rows):
        if (row % 10 == 0):
            print("  baris=",row,"dari",rows)
        for col in range(cols):
            p = (max(0, min(255, int(A_RD[row][col]))),
                 max(0, min(255, int(A_GR[row][col]))),
                 max(0, min(255, int(A_BL[row][col]))))
            img_squoze.putpixel((col,row), p)
    img_squoze.save(fn_out)
