window.tweak_content=function() {
    $('a:not(.internal-link, .anchor-link)').attr('target','_blank');
    $('a.anchor-link').click(function() {
        location.hash = $(this).attr('href');
        window.tweak_content();
        return false;
    });
    var anchor=location.hash;
    if (anchor) {
        window.SCROLLTO=anchor.slice(1);
        $('.hilite').removeClass('hilite');
        $(anchor).addClass('hilite').find('input.toggler').attr('checked','checked');
    }
    if (window.SCROLLTO!=undefined && window.SCROLLTO) {
     	$('html,body').animate({scrollTop: $("#"+window.SCROLLTO).offset().top-60},'slow');
    }
}
$(function() {
    $('body').append($('<a/>').attr('id','top-link').attr('href','#').addClass('internal-link').click(function() {
     	$('html,body').animate({scrollTop:0},'slow');
        return false;
    }).html('&#11014; Top'));
    $('#feed-url').click(function() {$(this).select()});
    window.tweak_content();
});
