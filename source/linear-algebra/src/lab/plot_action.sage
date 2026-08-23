# plot_action.sage
# 2012-Dec-04 JH
# 2019-Nov-25 JH

DOT_SIZE = .02
CIRCLE_THICKNESS = 2
def color_circle_list(a, b, c, d, colors, full_circle=False):
    """Kembalikan daftar objek grafik untuk aksi matriks 2x2 pada
    setengah lingkaran satuan. Lingkaran itu dibagi menjadi beberapa bagian
    yang masing-masing diberi warna berbeda.
      a, b, c, d  bilangan real  entri matriks kiri atas, kanan atas,
                    kiri bawah, kanan bawah
      colors  daftar tupel RGB; panjang daftar ini adalah banyaknya bagian
      full_circle=False  tampilkan satu lingkaran penuh sebagai gantinya
    """
    r = []
    if full_circle:
        p = 2*pi
    else:
        p = pi
    t = var('t')
    n = len(colors)
    for i in range(n):
        color = colors[i]
        x(t) = a*cos(t)+b*sin(t)
        y(t) = c*cos(t)+d*sin(t)
        g = parametric_plot((x(t), y(t)), 
                            (t, p*i/n, p*(i+1)/n), 
                            color = color, thickness=CIRCLE_THICKNESS)
        r.append(g)
        r.append(circle((x(p*i/n), y(p*i/n)), DOT_SIZE, color=color))
    if not(full_circle):    # tunjukkan bahwa (x,y)=(-1,0) tidak disertakan
        r.append(circle((x(pi), y(pi)), 2*DOT_SIZE, color='black', 
                        fill = 'true'))
        r.append(circle((x(pi), y(pi)), DOT_SIZE, color='white', 
                        fill = 'true'))
    return r


def plot_circle_action(a, b, c, d, n = 12, full_circle = False):
    """Tampilkan aksi matriks berentri a, b, c, d pada setengah lingkaran
    satuan yang dibagi menjadi beberapa warna.
     a, b, c, d  bilangan real  Entri berurutan dari kiri atas, kanan atas,
                    kiri bawah, kanan bawah.
     n = 12  bilangan bulat positif  Banyaknya warna.
     full_circle=False  boolean  Tampilkan seluruh lingkaran atau separuh atas
    """
    colors = rainbow(n)
    G = Graphics()  # menampung bagian-bagian grafik sampai ditampilkan
    for g_part in color_circle_list(a,b,c,d,colors,full_circle):
        G += g_part
    return plot(G)    


SQUARE_THICKNESS = 1.75  # ketebalan kurva yang digambar
ZORDER = 5    # gambar grafik di atas sumbu
def color_square_list(a, b, c, d, colors):
    """Kembalikan daftar objek grafik untuk aksi matriks 2x2 pada persegi
    satuan. Persegi itu dibagi menjadi sisi-sisi yang masing-masing diberi
    warna berbeda.
      a, b, c, d  bilangan real  entri matriks
      colors  daftar tupel RGB; panjang daftar ini sedikitnya empat
    """
    r = []
    t = var('t')
    # Empat sisi, berlawanan arah jarum jam mengelilingi persegi dari titik asal
    r.append(parametric_plot((a*t, c*t), (t, 0, 1), 
                             color = colors[0], zorder=ZORDER, 
                             thickness = SQUARE_THICKNESS))
    r.append(parametric_plot((a+b*t, c+d*t), (t, 0, 1), 
                             color = colors[1], zorder=ZORDER, 
                             thickness = SQUARE_THICKNESS))
    r.append(parametric_plot((a*(1-t)+b, c*(1-t)+d), (t, 0, 1), 
                              color = colors[2], zorder=ZORDER, 
                              thickness = SQUARE_THICKNESS))
    r.append(parametric_plot((b*(1-t), d*(1-t)), (t, 0, 1), 
                             color = colors[3], zorder=ZORDER, 
                             thickness = SQUARE_THICKNESS))
    # Titik-titik membuat sambungan antarsisi tampak lebih rapi
    r.append(circle((a, c), DOT_SIZE, 
                    color = colors[0], zorder = 2*ZORDER, 
                    thickness = SQUARE_THICKNESS*1.25, fill =  True))
    r.append(circle((a+b, c+d), DOT_SIZE, 
                    color = colors[1], zorder = 2*ZORDER+1, 
                    thickness = SQUARE_THICKNESS*1.25, fill =  True))
    r.append(circle((b, d), DOT_SIZE, 
                    color = colors[2], zorder = ZORDER+1, 
                    thickness = SQUARE_THICKNESS*1.25, fill =  True))
    r.append(circle((0, 0), DOT_SIZE, 
                    color = colors[3], zorder = ZORDER+1, 
                    thickness = SQUARE_THICKNESS*1.25, fill =  True))
    return r

def plot_square_action(a, b, c, d):
    """Tampilkan aksi matriks berentri a, b, c, d pada persegi satuan,
    dengan setiap sisi diberi warna berbeda.
     a, b, c, d  bilangan real  Entri berurutan dari kiri atas, kanan atas,
                    kiri bawah, kanan bawah.
    """
    colors = ['red', 'orange', 'green', 'blue']  
    G = Graphics()        # tampung bagian-bagian grafik sampai ditampilkan
    for g_part in color_square_list(a,b,c,d,colors):
        G += g_part
    p = plot(G)
    return p  

EPSILON = 0.25
ARROW_THICKNESS = .25
def point_list(a, b, c, d, pts, colors=None):
    """Tampilkan aksi matriks berentri a, b, c, d pada titik-titik.
      a, b, c, d  bilangan real  Kiri atas, kanan atas, kiri bawah,
                    kanan bawah, atau sebuah matriks.
      pts  daftar pasangan bilangan real
      colors = None  daftar warna
    """  
    r = []
    for dex, pt in enumerate(pts):
        x, y = pt
        f_x = a*x + b*y 
        f_y = c*x + d*y   
        if colors:
            color = colors[dex]
        else:
            color = 'lightgray'
        if ((abs(x-f_x) < EPSILON) and (abs(y-f_y) < EPSILON)):
            r.append(circle(pt, DOT_SIZE, color=color, 
                            thickness=ARROW_THICKNESS))
        else:
            r.append(arrow(pt, (f_x,f_y), color=color, 
                     width=ARROW_THICKNESS))
    return r

def point_grid(max_x, max_y):
    """Kembalikan sebuah kisi titik (x,y).
      max_x, max_y  bilangan bulat positif
    """
    r = []
    for x in range(-1*max_x,max_x+1):
        for y in range(-1*max_y,max_y+1):
            r.append((x,y))
    return r

def plot_point_action(a, b, c, d, pts,colors=None):
    """Tampilkan aksi matriks berentri a, b, c, d pada titik-titik.
      a, b, c, d  bilangan real  Kiri atas, kanan atas, kiri bawah,
                    kanan bawah, atau sebuah matriks.
      pts  daftar pasangan bilangan real
    """  
    if colors is None:
        colors = ["gray",]*len(pts)
    G =  Graphics()
    for action_arrow in point_list(a,b,c,d,pts,colors=colors):
        G += action_arrow
    p = plot(G)
    return p

BA_THICKNESS = 1.5
def before_after_list(a, b, c, d, pts, colors=None):
    """Tampilkan aksi matriks berentri a, b, c, d pada titik-titik dengan
    menggambar vektor sebelum dan sesudah aksi memakai warna yang sama.
      a, b, c, d  bilangan real  Kiri atas, kanan atas, kiri bawah,
                    kanan bawah, atau sebuah matriks.
      pts  daftar pasangan bilangan real
      colors = None  daftar warna
    """  
    r = []
    for dex, pt in enumerate(pts):
        x, y = pt
        v = vector(RDF, pt)
        M = matrix(RDF, [[a, b], [c, d]])
        f_x, f_y = M*v
        if colors:
            color = colors[dex]
        else:
            color = 'lightgray'
        if ((abs(x-f_x) < EPSILON) and (abs(y-f_y) < EPSILON)):
            r.append(circle(pt, DOT_SIZE, color=color, 
                            thickness=BA_THICKNESS))
        else:
            r.append(arrow((0,0), (x,y), color=color, 
                     width=BA_THICKNESS, arrowsize=2*BA_THICKNESS))
            r.append(arrow((0,0), (f_x,f_y), color=color, 
                     width=BA_THICKNESS, arrowsize=2*BA_THICKNESS))
    return r

def plot_before_after_action(a, b, c, d, pts, colors=None):
    """Tampilkan aksi matriks berentri a, b, c, d pada titik-titik.
      a, b, c, d  bilangan real  Kiri atas, kanan atas, kiri bawah,
                    kanan bawah, atau sebuah matriks.
      pts  daftar pasangan bilangan real; titik-titik awal yang ditampilkan
    """  
    if colors is None:
        colors = ["gray",]*len(pts)
    G =  Graphics()
    for ba in before_after_list(a,b,c,d,pts,colors=colors):
        G += ba
    p = plot(G)
    return p

# Cari sudut bertanda antara vektor bidang v dan Mv
# Lihat http://math.stackexchange.com/a/879474/12012
def find_angles(a,b,c,d,num_pts,lower_limit=None,upper_limit=None):
    """Terapkan matriks pada titik-titik di sepanjang setengah lingkaran atas,
    lalu kembalikan sudut antara vektor masukan dan vektor keluaran.
      a, b, c, d  bilangan real  Entri matriks kiri atas, kanan atas,
                    kiri bawah, kanan bawah.
      num_pts  bilangan bulat positif  banyaknya titik
      lower_limit=0, upper_limit=pi  abaikan sudut di luar batas-batas ini
    """
    if lower_limit is None:
        lower_limit=0
    if upper_limit is None:
        upper_limit=pi
    r = []
    M = Matrix(RDF, [[a, b], [c, d]])
    for i in range(num_pts):
        t = i*pi/num_pts
        if ((t<lower_limit) or (t>upper_limit)):
            continue
        pt = (cos(t), sin(t))
        v = vector(RDF, pt)
        w = M*v
        try:
            dot = v[0]*w[0] + v[1]*w[1]  # hasil kali titik
            det = v[0]*w[1] - v[1]*w[0]  # determinan
            angle = atan2(det, dot)      # atan2(y, x) atau atan2(sin, cos)
        except:
            angle = None
        r.append((t,angle))
    return r


MARKERSIZE = 2
TICKS = ([0,pi/4,pi/2,3*pi/4,pi], [0,pi/2,pi])
def color_angles_list(a, b, c, d, num_pts, colors):
    """Kembalikan daftar objek grafik untuk aksi matriks 2x2 pada setengah
    lingkaran satuan. Lingkaran itu dibagi menjadi beberapa bagian yang
    masing-masing diberi warna berbeda.
      a, b, c, d  bilangan real  entri matriks kiri atas, kanan atas,
                    kiri bawah, kanan bawah
      colors  daftar tupel RGB; panjang daftar ini adalah banyaknya bagian
    (Sangat tidak efisien; menjalankan scatter_points berkali-kali.)
    """
    r = []
    num_colors = len(colors)
    for i in range(num_colors):
        color = colors[i]
        points = find_angles(a,b,c,d,num_pts,
                             lower_limit=i*pi/num_colors,
                             upper_limit=(i+1)*pi/num_colors)
        g = scatter_plot(points,facecolor=color,edgecolor=color,
                         markersize=MARKERSIZE,ticks=TICKS) 
        r.append(g)
    return r

def plot_color_angles(a, b, c, d, num_points=1000):
    """Tampilkan aksi matriks berentri a, b, c, d pada setengah lingkaran
    satuan yang dibagi menjadi beberapa warna.
     a, b, c, d  bilangan real  Entri berurutan dari kiri atas, kanan atas,
                    kiri bawah, kanan bawah.
     num_points=1000  Banyaknya titik pada setengah lingkaran yang digambar
    """
    colors = rainbow(6)
    G = Graphics()  # menampung bagian-bagian grafik sampai ditampilkan
    for g_part in color_angles_list(a,b,c,d,num_points,colors):
        G += g_part
    return plot(G)    


plot.options['figsize'] = 2.5
plot.options['axes_pad'] = 0.05
plot.options['fontsize'] = 7
plot.options['dpi'] = 1200
plot.options['aspect_ratio'] = 1
